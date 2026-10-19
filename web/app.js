'use strict';

// ---------- helpers ----------
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const compact = new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 });
const fmt = (n) => (n == null || Number.isNaN(+n) ? '—' : compact.format(n));
const num = (n) => `<span class="num">${fmt(n)}</span>`;
const regionNames = new Intl.DisplayNames(['ar'], { type: 'region' });
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

function plural(n, one, few) { return `${n} ${n >= 3 && n <= 10 ? few : one}`; }

function ago(days) {
  if (days == null) return '—';
  if (days < 1) return 'النهارده';
  if (days < 2) return 'امبارح';
  if (days < 30) return 'من ' + plural(Math.floor(days), 'يوم', 'أيام');
  if (days < 365) return 'من ' + plural(Math.floor(days / 30), 'شهر', 'شهور');
  return `من ${(days / 365).toFixed(1)} سنة`;
}

function clock(sec) {
  sec = Math.round(sec || 0);
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  const mm = h ? String(m).padStart(2, '0') : m;
  return `<span class="num">${h ? h + ':' : ''}${mm}:${String(s).padStart(2, '0')}</span>`;
}

const loading = (msg = 'بيحمّل') => `<div class="loading">${esc(msg)}</div>`;
const errorBox = (msg) => `<div class="error-box">${esc(msg)}</div>`;
const empty = (msg) => `<div class="empty">${msg}</div>`;

function toast(msg) {
  const el = $('#toast');
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => { el.hidden = true; }, 2200);
}

async function copy(text, msg = 'اتنسخ') {
  await navigator.clipboard.writeText(text);
  toast(msg);
}

async function busy(btn, fn) {
  const label = btn.textContent;
  btn.disabled = true;
  btn.textContent = '...';
  try { return await fn(); } finally { btn.disabled = false; btn.textContent = label; }
}

async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  let data;
  try { data = await res.json(); } catch { data = { error: 'السيرفر رد برد مش مفهوم.' }; }
  if (!path.startsWith('/api/status') && !path.startsWith('/api/suggest')) loadStatus();
  if (!res.ok) {
    const err = new Error(data.error || (typeof data.detail === 'string' ? data.detail : 'حصلت مشكلة. جرّب تاني.'));
    err.auth = !!data.auth;
    throw err;
  }
  return data;
}

// ---------- status ----------
let status = {};

async function loadStatus() {
  try { status = await api('/api/status'); } catch { return; }
  const { used, limit } = status.quota;
  $('#quota-text').innerHTML = `<span class="num">${used.toLocaleString('en')} / ${limit.toLocaleString('en')}</span>`;
  $('#quota-bar').style.width = Math.min(100, (used / limit) * 100) + '%';
  $('#quota .bar').classList.toggle('warn', used / limit > 0.85);
  $('#setup-banner').hidden = status.has_key || location.hash === '#settings';
}

// ---------- shared renderers ----------
const vidId = (v) => v.id || v.video_id || v.video;

function ratioBadge(x) {
  if (x == null) return '—';
  const label = x >= 10 ? Math.round(x) : x.toFixed(1);
  return `<span class="badge ${x >= 3 ? 'hot' : ''} num">×${label}</span>`;
}

const COLUMNS = {
  video: {
    h: 'الفيديو', cls: 'title-cell',
    cell: (v) => `<a class="vid" href="https://www.youtube.com/watch?v=${esc(vidId(v))}" target="_blank" rel="noopener">
      <img src="${esc(v.thumbnail)}" loading="lazy" alt="">
      <div><div class="t">${esc(v.title)}</div>
      <div class="c">${esc(v.channel_title || '')}${v.duration ? ' · ' + clock(v.duration) : ''}</div></div></a>`,
  },
  views: { h: 'المشاهدات', cell: (v) => num(v.views) },
  vpd: { h: 'مشاهدة/يوم', cell: (v) => num(v.vpd) },
  age: { h: 'اتنشر', cell: (v) => ago(v.age_days) },
  subs: { h: 'مشتركين القناة', cell: (v) => num(v.subs) },
  ratio: { h: 'مشاهدات ÷ مشتركين', cell: (v) => ratioBadge(v.outlier) },
  outlier: { h: 'مقارنة بالمعتاد', cell: (v) => ratioBadge(v.outlier) },
  match: { h: 'الكلمة في العنوان', cell: (v) => (v.title_match ? '<span class="yes">✓</span>' : '<span class="no">—</span>') },
  growth: { h: 'زيادة/يوم', cell: (v) => (v.growth_per_day == null ? '<span class="muted small">بعد تحديث بكرة</span>' : num(v.growth_per_day)) },
};

function table(rows, keys) {
  const cols = keys.map((k) => (typeof k === 'string' ? COLUMNS[k] : k));
  return `<div class="table-wrap"><table>
    <thead><tr>${cols.map((c) => `<th>${c.h}</th>`).join('')}</tr></thead>
    <tbody>${rows.map((r) => `<tr>${cols.map((c) => `<td class="${c.cls || ''}">${c.cell(r)}</td>`).join('')}</tr>`).join('')}</tbody>
  </table></div>`;
}

function tone(value, invert = false) {
  const v = invert ? 100 - value : value;
  return v >= 65 ? 'good' : v >= 40 ? 'mid' : 'bad';
}

function scoreCard(label, value, sub, invert = false) {
  const t = tone(value, invert);
  return `<div class="panel kpi">
    <div class="label">${label}</div>
    <div class="score-big ${t} num">${value}</div>
    <div class="meter ${t === 'bad' ? 'rust' : ''}"><span style="width:${value}%"></span></div>
    <div class="sub">${sub}</div>
  </div>`;
}

function statCard(label, value, sub = '') {
  return `<div class="panel kpi"><div class="label">${label}</div><div class="value">${value}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`;
}

function bars(rows, { best = true } = {}) {
  const max = Math.max(...rows.map((r) => r.value || 0), 0) || 1;
  const top = best ? Math.max(...rows.map((r) => r.value || 0)) : null;
  return `<div class="bars">${rows.map((r) => `
    <div class="bar-row ${best && r.value === top && r.value ? 'best' : ''}">
      <span><bdi>${esc(r.label)}</bdi></span>
      <div class="bar"><span style="width:${((r.value || 0) / max) * 100}%"></span></div>
      <span class="v">${r.text}</span>
    </div>`).join('')}</div>`;
}

function renderSeo(seo) {
  const t = tone(seo.score);
  const label = seo.score >= 80 ? 'ممتاز' : seo.score >= 60 ? 'كويس' : seo.score >= 40 ? 'محتاج شغل' : 'ضعيف';
  const groups = [...new Set(seo.checks.map((c) => c.group))];
  return `
    <div class="panel-head"><h2>تقييم الـ SEO</h2><span class="muted small">${label}</span></div>
    <div class="score-big ${t} num">${seo.score}</div>
    <div class="meter ${t === 'bad' ? 'rust' : ''}"><span style="width:${seo.score}%"></span></div>
    ${seo.needs_keyword ? '<p class="muted small">اكتب الكلمة المستهدفة عشان يتفحص مكانها في العنوان والوصف والتاجز.</p>' : ''}
    <div class="checks">${groups.map((g) => `<h3>${g}</h3>${seo.checks.filter((c) => c.group === g).map((c) => `
      <div class="check ${c.status}"><span class="mark"></span><span>${esc(c.label)}</span>${c.tip ? `<span class="tip">${esc(c.tip)}</span>` : ''}</div>`).join('')}`).join('')}
    </div>`;
}

// ---------- router ----------
const VIEWS = ['keywords', 'video', 'seo', 'competitors', 'me', 'settings'];
const onEnter = {
  competitors: () => loadCompetitors(),
  me: () => loadMe(),
  settings: () => fillSettings(),
};

function route() {
  const name = VIEWS.includes(location.hash.slice(1)) ? location.hash.slice(1) : 'keywords';
  VIEWS.forEach((v) => { $(`#view-${v}`).hidden = v !== name; });
  $$('nav a').forEach((a) => a.classList.toggle('active', a.dataset.view === name));
  $('#setup-banner').hidden = status.has_key !== false || name === 'settings';
  onEnter[name]?.();
}

// ---------- keywords ----------
const kwInput = $('#kw-input');
const kwDropdown = $('#kw-dropdown');
let dropIndex = -1;

function hideDropdown() { kwDropdown.hidden = true; dropIndex = -1; }

const liveSuggest = debounce(async () => {
  const q = kwInput.value.trim();
  if (q.length < 2) return hideDropdown();
  try {
    const items = await api(`/api/suggest?q=${encodeURIComponent(q)}`);
    if (kwInput.value.trim() !== q || !items.length) return hideDropdown();
    kwDropdown.innerHTML = items.map((s) => `<li>${esc(s)}</li>`).join('');
    kwDropdown.hidden = false;
    dropIndex = -1;
  } catch { hideDropdown(); }
}, 220);

kwInput.addEventListener('input', liveSuggest);
kwInput.addEventListener('keydown', (e) => {
  const items = $$('li', kwDropdown);
  if (kwDropdown.hidden || !items.length) return;
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault();
    dropIndex = (dropIndex + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
    items.forEach((li, i) => li.classList.toggle('active', i === dropIndex));
    kwInput.value = items[dropIndex].textContent;
  } else if (e.key === 'Escape') hideDropdown();
});
kwDropdown.addEventListener('mousedown', (e) => {
  const li = e.target.closest('li');
  if (li) { e.preventDefault(); analyzeKeyword(li.textContent); }
});
kwInput.addEventListener('blur', () => setTimeout(hideDropdown, 150));
$('#kw-form').addEventListener('submit', (e) => { e.preventDefault(); analyzeKeyword(kwInput.value); });

async function analyzeKeyword(q) {
  q = q.trim();
  if (!q) return;
  kwInput.value = q;
  hideDropdown();
  if (location.hash !== '#keywords') location.hash = '#keywords';
  const box = $('#kw-result');
  box.innerHTML = loading('بيحلل أول 25 نتيجة في البحث');
  try {
    const d = await api(`/api/keywords/analyze?q=${encodeURIComponent(q)}`);
    box.innerHTML = renderKeyword(d);
  } catch (e) {
    box.innerHTML = errorBox(e.message);
  }
}

function keywordChips(list) {
  return `<div class="chips">${list.map((s) => `<button class="chip" data-analyze="${esc(s)}" title="حلل (حوالي 102 وحدة)">${esc(s)}</button>`).join('')}</div>`;
}

function renderKeyword(d) {
  if (d.empty) return empty('مفيش نتايج في البحث للكلمة دي.') + (d.suggestions.length ? `<div class="panel">${keywordChips(d.suggestions)}</div>` : '');
  const s = d.scores, st = d.stats;
  return `
    <div class="grid kpis">
      ${scoreCard('التقييم العام', s.overall, `${s.overall_label}: الطلب قصاد المنافسة`)}
      ${scoreCard('الطلب (تقدير)', s.demand, 'من سرعة مشاهدات أول النتايج واقتراحات البحث')}
      ${scoreCard('المنافسة', s.competition, 'من حجم القنوات اللي في أول النتايج', true)}
    </div>
    <div class="grid kpis">
      ${statCard('متوسط مشاهدات/يوم لأول 10', num(st.median_vpd))}
      ${statCard('متوسط مشتركين قنواتهم', num(st.median_subs))}
      ${statCard('عناوين فيها الكلمة', `<span class="num">${st.match_pct}%</span>`)}
      ${statCard('أحدث من 6 شهور', `<span class="num">${st.fresh_pct}%</span>`)}
      ${statCard('قنوات صغيرة في أول 10', `<span class="num">${st.small_channels}</span>`, 'أقل من 10K مشترك')}
    </div>
    ${d.notes.length ? `<div class="panel"><ul class="notes">${d.notes.map((n) => `<li>${esc(n)}</li>`).join('')}</ul></div>` : ''}
    <div class="grid two">
      <div class="panel">
        <div class="panel-head"><h2>كلمات قريبة</h2><button class="btn small" data-explore="${esc(d.keyword)}">وسّع الاقتراحات</button></div>
        ${d.suggestions.length ? keywordChips(d.suggestions) : '<p class="muted small">مفيش اقتراحات.</p>'}
        <div class="explore"></div>
      </div>
      <div class="panel">
        <div class="panel-head"><h2>التاجز الأكتر استخدامًا</h2>
          ${d.tags.length ? `<button class="btn small" data-copy="${esc(d.tags.map((t) => t.tag).join(', '))}">انسخ الكل</button>` : ''}</div>
        ${d.tags.length ? `<div class="chips">${d.tags.map((t) => `<button class="chip" data-copy="${esc(t.tag)}">${esc(t.tag)}<span class="count num">${t.count}</span></button>`).join('')}</div>`
          : '<p class="muted small">الفيديوهات دي مش حاطة تاجز.</p>'}
        <p class="muted small">الرقم جنب التاج = عدد الفيديوهات اللي مستخدماه من أول 25. اضغط على التاج تنسخه.</p>
      </div>
    </div>
    <div class="section-head"><h2>أول 25 نتيجة في البحث</h2></div>
    ${table(d.videos, ['video', 'views', 'vpd', 'age', 'subs', 'ratio', 'match'])}`;
}

$('#kw-result').addEventListener('click', async (e) => {
  const chip = e.target.closest('[data-analyze]');
  if (chip) return analyzeKeyword(chip.dataset.analyze);
  const ex = e.target.closest('[data-explore]');
  if (ex) {
    const box = $('.explore', ex.closest('.panel'));
    await busy(ex, async () => {
      box.innerHTML = loading('بيجمع الاقتراحات');
      try {
        const ideas = await api(`/api/keywords/explore?q=${encodeURIComponent(ex.dataset.explore)}`);
        box.innerHTML = ideas.length ? `<h3 class="muted">${ideas.length} فكرة من اقتراحات البحث</h3>${keywordChips(ideas)}` : '<p class="muted small">مفيش اقتراحات زيادة.</p>';
      } catch (err) { box.innerHTML = errorBox(err.message); }
    });
  }
});

// Copy buttons anywhere on the page.
document.addEventListener('click', (e) => {
  const btn = e.target.closest('[data-copy]');
  if (btn) copy(btn.dataset.copy);
});

// ---------- single video ----------
$('#video-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const url = $('#video-url').value.trim();
  if (!url) return;
  const box = $('#video-result');
  box.innerHTML = loading();
  try {
    const v = await api(`/api/video?url=${encodeURIComponent(url)}&keyword=${encodeURIComponent($('#video-keyword').value)}`);
    box.innerHTML = renderVideo(v);
    box._video = v;
  } catch (err) { box.innerHTML = errorBox(err.message); }
});

function renderVideo(v) {
  const ch = v.channel;
  const tagsText = v.tags.join(', ');
  return `
    <div class="panel video-card">
      <a href="https://www.youtube.com/watch?v=${esc(v.id)}" target="_blank" rel="noopener"><img src="${esc(v.thumbnail)}" alt=""></a>
      <div class="view">
        <h2>${esc(v.title)}</h2>
        <div class="muted small">${esc(ch.title)} · ${num(ch.subs)} مشترك · ${ago(v.age_days)} · ${clock(v.duration)}${v.is_short ? ' · شورت' : ''}</div>
        <div class="grid kpis">
          ${statCard('المشاهدات', num(v.views))}
          ${statCard('مشاهدة/يوم', num(v.vpd))}
          ${statCard('مقارنة بالمعتاد للقناة', ratioBadge(v.outlier), `المعتاد ${fmt(ch.median_views)} مشاهدة`)}
          ${statCard('التفاعل', `<span class="num">${v.engagement}%</span>`, `${fmt(v.likes)} لايك · ${fmt(v.comments)} كومنت`)}
        </div>
        <div><button class="btn small" id="video-to-seo">افتحه في SEO</button></div>
      </div>
    </div>
    <div class="grid two">
      <div class="panel">
        <div class="panel-head"><h2>التاجز (${v.tags.length})</h2>${v.tags.length ? `<button class="btn small" data-copy="${esc(tagsText)}">انسخ الكل</button>` : ''}</div>
        ${v.tags.length ? `<div class="chips">${v.tags.map((t) => `<button class="chip" data-copy="${esc(t)}">${esc(t)}</button>`).join('')}</div>` : '<p class="muted small">الفيديو ده مفيهوش تاجز.</p>'}
        <details><summary class="muted small">الوصف</summary><p style="white-space:pre-wrap">${esc(v.description)}</p></details>
      </div>
      <div class="panel">${renderSeo(v.seo)}</div>
    </div>`;
}

$('#video-result').addEventListener('click', (e) => {
  if (e.target.id !== 'video-to-seo') return;
  const v = $('#video-result')._video;
  fillSeoForm(v, $('#video-keyword').value);
  location.hash = '#seo';
});

// ---------- SEO ----------
const seoForm = $('#seo-form');
const LIMITS = { title: 100, description: 5000, tags: 500 };

function seoValues() {
  const f = new FormData(seoForm);
  return {
    title: f.get('title'),
    description: f.get('description'),
    tags: f.get('tags').split(/[,،\n]/).map((t) => t.trim()).filter(Boolean),
    keyword: f.get('keyword'),
  };
}

function updateCounters(counts) {
  for (const [key, limit] of Object.entries(LIMITS)) {
    const el = $(`.counter[data-for="${key}"]`);
    const n = counts[key];
    el.textContent = `${n}/${limit}`;
    el.classList.toggle('over', n > limit);
  }
}

const scoreSeo = debounce(async () => {
  try {
    const res = await api('/api/seo', { method: 'POST', body: seoValues() });
    $('#seo-score').innerHTML = renderSeo(res);
    updateCounters(res.counts);
  } catch (err) { $('#seo-score').innerHTML = errorBox(err.message); }
}, 300);

seoForm.addEventListener('input', scoreSeo);

function fillSeoForm(v, keyword = '') {
  seoForm.title.value = v.title;
  seoForm.description.value = v.description;
  seoForm.tags.value = v.tags.join(', ');
  if (keyword) seoForm.keyword.value = keyword;
  scoreSeo();
}

$('#seo-load').addEventListener('click', (e) => busy(e.target, async () => {
  const url = $('#seo-load-url').value.trim();
  if (!url) return;
  try {
    fillSeoForm(await api(`/api/video?url=${encodeURIComponent(url)}`));
    toast('اتحمّل');
  } catch (err) { toast(err.message); }
}));

// ---------- competitors ----------
async function loadCompetitors() {
  const box = $('#comp-list');
  try {
    const list = await api('/api/competitors');
    box.innerHTML = list.length ? list.map((c) => `
      <div class="panel comp">
        <img src="${esc(c.thumbnail)}" alt="" loading="lazy">
        <div class="info">
          <a class="name" href="https://www.youtube.com/channel/${esc(c.channel_id)}" target="_blank" rel="noopener">${esc(c.title)}</a>
          <div class="meta">${num(c.subs)} مشترك · المعتاد ${num(c.median_views)} مشاهدة</div>
          <div class="meta">${plural(c.uploads_30d, 'فيديو', 'فيديوهات')} آخر 30 يوم</div>
        </div>
        <button class="btn ghost" data-remove="${esc(c.channel_id)}" title="شيل القناة">✕</button>
      </div>`).join('') : empty('لسه مضفتش منافسين. ابدأ بـ 3-5 قنوات في نفس مجالك.');
    const select = $('#out-channel');
    const current = select.value;
    select.innerHTML = '<option value="">كل القنوات</option>' + list.map((c) => `<option value="${esc(c.channel_id)}">${esc(c.title)}</option>`).join('');
    select.value = current;
    $('#comp-insights').hidden = !list.length;
    if (list.length) { loadOutliers(); loadTiming(); }
  } catch (err) { box.innerHTML = errorBox(err.message); }
}

async function loadOutliers() {
  const box = $('#out-list');
  const q = new URLSearchParams({ days: $('#out-days').value, format: $('#out-format').value, channel: $('#out-channel').value });
  try {
    const rows = await api(`/api/outliers?${q}`);
    box.innerHTML = rows.length ? table(rows, ['video', 'outlier', 'views', 'vpd', 'growth', 'age']) : empty('مفيش فيديوهات في الفترة دي.');
  } catch (err) { box.innerHTML = errorBox(err.message); }
}

async function loadTiming() {
  const box = $('#timing');
  try {
    const t = await api('/api/timing');
    if (t.sample < 20) {
      box.innerHTML = empty(`محتاج 20 فيديو طويل على الأقل من المنافسين عشان النتيجة يبقى ليها معنى (عندك ${t.sample}). ضيف قنوات أكتر.`);
      return;
    }
    const toBars = (list) => bars(list.map((r) => ({ label: r.label, value: r.score, text: r.score ? `×${r.score.toFixed(1)} · ${r.count}` : '—' })));
    box.innerHTML = `
      <p class="muted small">ده متوسط أداء فيديوهات المنافسين حسب وقت نشرها (بتوقيتك)، من ${t.sample} فيديو. ×1.0 = المعتاد. أدق مصدر لجمهورك إنت هو «جمهورك موجود على يوتيوب إمتى» في YouTube Studio.</p>
      <div class="grid two">
        <div class="panel"><h3>حسب اليوم</h3>${toBars(t.weekdays)}</div>
        <div class="panel"><h3>حسب الساعة</h3>${toBars(t.hours)}</div>
      </div>`;
  } catch (err) { box.innerHTML = errorBox(err.message); }
}

$('#comp-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = $('#comp-input');
  if (!input.value.trim()) return;
  await busy($('button[type=submit]', e.target), async () => {
    try {
      const c = await api('/api/competitors', { method: 'POST', body: { query: input.value } });
      input.value = '';
      toast(`اتضافت ${c.title}`);
      loadCompetitors();
    } catch (err) { toast(err.message); }
  });
});

$('#comp-refresh').addEventListener('click', (e) => busy(e.target, async () => {
  try {
    const r = await api('/api/competitors/refresh', { method: 'POST' });
    toast(`اتحدّث ${r.refreshed} قناة`);
    loadCompetitors();
  } catch (err) { toast(err.message); }
}));

$('#comp-list').addEventListener('click', async (e) => {
  const btn = e.target.closest('[data-remove]');
  if (!btn || !confirm('تشيل القناة دي وكل بياناتها؟')) return;
  await api(`/api/competitors/${btn.dataset.remove}`, { method: 'DELETE' });
  loadCompetitors();
});

['#out-days', '#out-format', '#out-channel'].forEach((s) => $(s).addEventListener('change', loadOutliers));

// ---------- my channel ----------
const meRoot = $('#me-root');
let meDays = 28;
let meLoaded = false;

function connectPanel(message = '') {
  const steps = status.has_client
    ? `<p>اربط قناتك عشان تشوف أرقامها الحقيقية: الكلمات اللي الناس بحثت بيها ووصلتلك، مصادر المشاهدات، وأداء كل فيديو.</p>
       <p class="muted small">الصلاحية قراءة بس. البرنامج مش بيقدر يعدّل أو ينشر حاجة على قناتك.</p>
       <div><a class="btn primary" href="/auth/login">اربط قناتك</a></div>`
    : `<p>عشان تربط قناتك محتاج <b>OAuth Client ID</b> و <b>Client Secret</b>.</p>
       <div><a class="btn primary" href="#settings">روح للإعدادات</a></div>`;
  return `<header class="view-head"><h1>قناتي</h1></header>
    ${message ? errorBox(message) : ''}
    <div class="panel">${steps}</div>`;
}

async function loadMe(force = false) {
  if (meLoaded && !force) return;
  await loadStatus();
  if (!status.has_client || !status.connected) { meRoot.innerHTML = connectPanel(); return; }
  meRoot.innerHTML = loading();
  let me;
  try { me = await api('/api/me'); } catch (err) {
    meRoot.innerHTML = err.auth ? connectPanel(err.message) : errorBox(err.message);
    return;
  }
  meLoaded = true;
  meRoot.innerHTML = `
    <div class="me-head">
      <img src="${esc(me.thumbnail)}" alt="">
      <div class="grow"><h1>${esc(me.title)}</h1>
        <div class="muted small">${num(me.subs)} مشترك · ${num(me.view_count)} مشاهدة · ${plural(me.video_count, 'فيديو', 'فيديوهات')}</div></div>
      <select id="me-days">
        ${[7, 28, 90, 365].map((d) => `<option value="${d}" ${d === meDays ? 'selected' : ''}>آخر ${d} يوم</option>`).join('')}
      </select>
      <button class="btn ghost" id="me-logout">افصل القناة</button>
    </div>
    <div id="me-overview">${loading()}</div>
    <div class="grid two">
      <div class="panel"><div class="panel-head"><h2>الناس بحثت عن إيه ووصلتلك</h2></div>
        <p class="muted small">دي الكلمات الحقيقية من بحث يوتيوب. اضغط «حلل» عشان تشوف فرصتها.</p>
        <div id="me-terms">${loading()}</div></div>
      <div class="panel"><h2>المشاهدات جاية منين</h2><div id="me-traffic">${loading()}</div></div>
    </div>
    <div class="section-head"><h2>أداء الفيديوهات في الفترة دي</h2></div>
    <div id="me-videos">${loading()}</div>
    <div class="section-head"><h2>الجمهور</h2></div>
    <div id="me-audience">${loading()}</div>`;
  $('#me-days').addEventListener('change', (e) => { meDays = +e.target.value; loadMeSections(); });
  $('#me-logout').addEventListener('click', async () => {
    if (!confirm('تفصل القناة من البرنامج؟')) return;
    await api('/auth/logout', { method: 'POST' });
    meLoaded = false;
    loadMe(true);
  });
  loadMeSections();
}

function section(id, path, render) {
  const box = $(id);
  box.innerHTML = loading();
  api(`${path}?days=${meDays}`)
    .then((data) => { box.innerHTML = render(data); })
    .catch((err) => {
      box.innerHTML = errorBox(err.message) + (err.auth ? '<p><a class="btn primary" href="/auth/login">اربط القناة تاني</a></p>' : '');
    });
}

function delta(cur, prev) {
  if (!prev) return '';
  const d = ((cur - prev) / prev) * 100;
  return `<span class="delta ${d >= 0 ? 'up' : 'down'} num">${d >= 0 ? '+' : ''}${d.toFixed(0)}%</span> عن الفترة اللي قبلها`;
}

function lineChart(points) {
  if (points.length < 2) return '';
  const W = 800, H = 220, P = { t: 12, r: 12, b: 26, l: 44 };
  const max = Math.max(...points.map((p) => p.value), 1);
  const x = (i) => P.l + (i / (points.length - 1)) * (W - P.l - P.r);
  const y = (v) => H - P.b - (v / max) * (H - P.t - P.b);
  const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join('');
  const area = `${line}L${x(points.length - 1)},${H - P.b}L${x(0)},${H - P.b}Z`;
  const ticks = [0, Math.floor((points.length - 1) / 2), points.length - 1];
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" dir="ltr" role="img" aria-label="المشاهدات اليومية">
    <line x1="${P.l}" x2="${W - P.r}" y1="${y(max)}" y2="${y(max)}" stroke="var(--line)" stroke-dasharray="3 4"/>
    <line x1="${P.l}" x2="${W - P.r}" y1="${H - P.b}" y2="${H - P.b}" stroke="var(--line)"/>
    <path d="${area}" fill="var(--champagne-veil)"/>
    <path d="${line}" fill="none" stroke="var(--champagne)" stroke-width="2" stroke-linejoin="round"/>
    <text x="${P.l - 8}" y="${y(max) + 4}" text-anchor="end">${fmt(max)}</text>
    <text x="${P.l - 8}" y="${H - P.b + 4}" text-anchor="end">0</text>
    ${ticks.map((i) => `<text x="${x(i)}" y="${H - 6}" text-anchor="middle">${points[i].label}</text>`).join('')}
  </svg>`;
}

function loadMeSections() {
  section('#me-overview', '/api/me/overview', (o) => {
    const c = o.current, p = o.previous;
    const net = (r) => (r.subscribersGained || 0) - (r.subscribersLost || 0);
    return `
      <p class="muted small">من ${o.start} لـ ${o.end}. أرقام يوتيوب بتتأخر حوالي يومين.</p>
      <div class="grid kpis">
        ${statCard('المشاهدات', num(c.views), delta(c.views, p.views))}
        ${statCard('ساعات المشاهدة', num((c.estimatedMinutesWatched || 0) / 60), delta(c.estimatedMinutesWatched, p.estimatedMinutesWatched))}
        ${statCard('صافي المشتركين', `<span class="num">${net(c) >= 0 ? '+' : ''}${fmt(net(c))}</span>`, delta(net(c), net(p)))}
        ${statCard('متوسط مدة المشاهدة', clock(c.averageViewDuration), delta(c.averageViewDuration, p.averageViewDuration))}
        ${statCard('متوسط نسبة المشاهدة', `<span class="num">${(c.averageViewPercentage || 0).toFixed(1)}%</span>`)}
      </div>
      <div class="panel"><h3 class="muted">المشاهدات اليومية</h3>${lineChart(o.daily.map((d) => ({ label: d.day.slice(5), value: d.views })))}</div>`;
  });

  section('#me-terms', '/api/me/search-terms', (rows) => rows.length ? table(rows, [
    { h: 'الكلمة', cell: (r) => esc(r.insightTrafficSourceDetail) },
    { h: 'المشاهدات', cell: (r) => num(r.views) },
    { h: '', cell: (r) => `<button class="btn small" data-analyze-term="${esc(r.insightTrafficSourceDetail)}">حلل</button>` },
  ]) : empty('مفيش مشاهدات من البحث في الفترة دي.'));

  section('#me-traffic', '/api/me/traffic', (rows) => {
    const total = rows.reduce((s, r) => s + r.views, 0) || 1;
    return rows.length ? bars(rows.map((r) => ({ label: r.label, value: r.views, text: `${((r.views / total) * 100).toFixed(0)}%` })), { best: false }) : empty('مفيش داتا.');
  });

  section('#me-videos', '/api/me/videos', (rows) => rows.length ? table(rows, [
    'video', 'views',
    { h: 'ساعات المشاهدة', cell: (r) => num(r.estimatedMinutesWatched / 60) },
    { h: 'متوسط المدة', cell: (r) => clock(r.averageViewDuration) },
    { h: 'نسبة المشاهدة', cell: (r) => `<span class="num">${r.averageViewPercentage.toFixed(0)}%</span>` },
    { h: 'مشتركين جداد', cell: (r) => num(r.subscribersGained) },
  ]) : empty('مفيش مشاهدات في الفترة دي.'));

  section('#me-audience', '/api/me/audience', (a) => {
    const byAge = {}, byGender = {};
    for (const r of a.demographics) {
      const age = r.ageGroup.replace('age', '').replace('-', '–');
      byAge[age] = (byAge[age] || 0) + r.viewerPercentage;
      byGender[r.gender] = (byGender[r.gender] || 0) + r.viewerPercentage;
    }
    const genderLabel = { male: 'رجالة', female: 'ستات', user_specified: 'محدد من المستخدم' };
    const totalViews = a.countries.reduce((s, r) => s + r.views, 0) || 1;
    return `<div class="grid two">
      <div class="panel"><h3>أكتر الدول</h3>${a.countries.length ? bars(a.countries.map((r) => {
        let name = r.country;
        try { name = regionNames.of(r.country); } catch { /* unknown code */ }
        return { label: name, value: r.views, text: `${fmt(r.views)}` };
      }), { best: false }) : empty('مفيش داتا.')}<p class="muted small">النسب من أول 10 دول بس (${fmt(totalViews)} مشاهدة).</p></div>
      <div class="panel"><h3>السن والنوع</h3>${Object.keys(byAge).length
        ? bars(Object.entries(byAge).map(([k, v]) => ({ label: k, value: v, text: `${v.toFixed(0)}%` })), { best: false })
          + bars(Object.entries(byGender).map(([k, v]) => ({ label: genderLabel[k] || k, value: v, text: `${v.toFixed(0)}%` })), { best: false })
        : empty('يوتيوب مش بيعرض السن والنوع غير لما يبقى فيه مشاهدات كفاية.')}</div>
    </div>`;
  });
}

meRoot.addEventListener('click', (e) => {
  const btn = e.target.closest('[data-analyze-term]');
  if (btn) analyzeKeyword(btn.dataset.analyzeTerm);
});

// ---------- settings ----------
function fillSettings() {
  loadStatus().then(() => {
    const pill = (el, ok) => { el.textContent = ok ? 'متسجل' : 'مش موجود'; el.classList.toggle('ok', ok); };
    pill($('#st-key'), status.has_key);
    pill($('#st-client'), status.has_client);
    $('#settings-form').region.placeholder = status.region;
    $('#settings-form').lang.placeholder = status.lang;
  });
}

$('#settings-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const form = e.target;
  const body = Object.fromEntries(new FormData(form));
  await busy($('button[type=submit]', form), async () => {
    try {
      await api('/api/settings', { method: 'POST', body });
      $$('input', form).forEach((i) => { i.value = ''; });
      toast('اتحفظ');
      meLoaded = false;
      fillSettings();
    } catch (err) { $('#settings-msg').textContent = err.message; }
  });
});

// ---------- start ----------
window.addEventListener('hashchange', route);
loadStatus().then(route);
scoreSeo();
