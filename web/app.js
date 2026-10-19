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
  const badge = $('#alert-count');
  badge.textContent = status.unread_alerts;
  badge.hidden = !status.unread_alerts;
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
  vph: { h: 'مشاهدة/ساعة', cell: (v) => (v.vph == null ? '<span class="muted small">—</span>' : num(v.vph)) },
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
const VIEWS = ['ideas', 'keywords', 'write', 'thumb', 'seo', 'video', 'competitors', 'me', 'edit', 'ranks', 'settings'];
// Pages in other files (ideas.js, write.js, thumb.js, channel.js, edit.js, ranks.js) register their own entries.
const onEnter = {
  competitors: () => loadCompetitors(),
  seo: () => loadTagLists(),
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
    <div class="row-inline wrap">
      <button class="btn small" data-plan-kw="${esc(d.keyword)}">ضيفها لمخطط الفيديوهات</button>
      <button class="btn small" data-write-kw="${esc(d.keyword)}">اكتب عناوين ليها بالـ AI</button>
    </div>
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
  const plan = e.target.closest('[data-plan-kw]');
  if (plan) {
    await api('/api/ideas', { method: 'POST', body: { title: plan.dataset.planKw, keyword: plan.dataset.planKw, source: 'keyword' } });
    plan.disabled = true;
    plan.textContent = 'اتضافت للمخطط';
    return;
  }
  const write = e.target.closest('[data-write-kw]');
  if (write) return openWriter({ topic: write.dataset.writeKw, keyword: write.dataset.writeKw });
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
        <div class="row-inline wrap">
          <button class="btn small" id="video-to-seo">افتحه في SEO</button>
          <button class="btn small" id="video-comments">حلل الكومنتات</button>
          <button class="btn small" id="video-retention" title="لفيديوهات قناتك بس، ومحتاج تربط القناة">الناس بتمشي فين؟</button>
        </div>
      </div>
    </div>
    <div id="video-extra"></div>
    <div class="grid two">
      <div class="panel">
        <div class="panel-head"><h2>التاجز (${v.tags.length})</h2>${v.tags.length ? `<button class="btn small" data-copy="${esc(tagsText)}">انسخ الكل</button>` : ''}</div>
        ${v.tags.length ? `<div class="chips">${v.tags.map((t) => `<button class="chip" data-copy="${esc(t)}">${esc(t)}</button>`).join('')}</div>` : '<p class="muted small">الفيديو ده مفيهوش تاجز.</p>'}
        <details><summary class="muted small">الوصف</summary><p style="white-space:pre-wrap">${esc(v.description)}</p></details>
      </div>
      <div class="panel">${renderSeo(v.seo)}</div>
    </div>`;
}

$('#video-result').addEventListener('click', async (e) => {
  const v = $('#video-result')._video;
  if (e.target.id === 'video-to-seo') {
    fillSeoForm(v, $('#video-keyword').value);
    location.hash = '#seo';
  } else if (e.target.id === 'video-comments') {
    const box = $('#video-extra');
    box.innerHTML = loading('بيقرا الكومنتات');
    try {
      box.innerHTML = renderComments(await api(`/api/comments?url=${v.id}&ai=${status.has_ai ? 1 : 0}`));
    } catch (err) { box.innerHTML = errorBox(err.message); }
  } else if (e.target.id === 'video-retention') {
    const box = $('#video-extra');
    box.innerHTML = loading();
    try {
      box.innerHTML = renderRetention(await api(`/api/retention?url=${v.id}`));
    } catch (err) {
      box.innerHTML = errorBox(err.message) + (err.auth ? '<p><a class="btn primary" href="/auth/login">اربط قناتك</a></p>' : '');
    }
  }
});

function commentList(rows) {
  if (!rows.length) return '<p class="muted small">مفيش.</p>';
  return `<div class="notes">${rows.map((c) => `<div class="idea"><span>${esc(c.text.slice(0, 280))}</span><span class="muted small">${esc(c.author)} · ${fmt(c.likes)} لايك</span></div>`).join('')}</div>`;
}

function renderComments(d) {
  const a = d.ai;
  const aiPanel = a ? `
    <div class="panel">
      <div class="panel-head"><h2>ملخص الـ AI</h2><span class="usage num">$${a.usage.cost_usd}</span></div>
      <p>${esc(a.summary)}</p>
      <div class="muted small">إيجابي ${a.sentiment.positive}% · محايد ${a.sentiment.neutral}% · سلبي ${a.sentiment.negative}%</div>
      ${a.video_ideas.length ? `<h3>أفكار فيديوهات من الكومنتات</h3><ul class="notes">${a.video_ideas.map((i) => `<li>${esc(i)}</li>`).join('')}</ul>` : ''}
      ${a.requests.length ? `<h3>طلبات المشاهدين</h3><ul class="notes">${a.requests.map((i) => `<li>${esc(i)}</li>`).join('')}</ul>` : ''}
    </div>` : '<p class="muted small">حط Claude API key في الإعدادات عشان يطلعلك ملخص وأفكار من الكومنتات.</p>';
  return `
    <div class="section-head"><h2>الكومنتات (${d.count})</h2></div>
    ${aiPanel}
    <div class="grid two">
      <div class="panel"><h3>أكتر الكلمات</h3><div class="chips">${d.words.map((w) => `<span class="chip">${esc(w.word)}<span class="count num">${w.count}</span></span>`).join('')}</div></div>
      <div class="panel"><h3>طلبات (اعمل، ياريت، عايزين...)</h3>${commentList(d.requests)}</div>
      <div class="panel"><h3>أسئلة</h3>${commentList(d.questions)}</div>
      <div class="panel"><h3>الأكتر لايكات</h3>${commentList(d.top)}</div>
    </div>`;
}

function retentionChart(points, duration) {
  if (points.length < 2) return '';
  const W = 800, H = 220, P = { t: 12, r: 12, b: 26, l: 44 };
  const max = Math.max(100, ...points.map((p) => p.pct));
  const x = (t) => P.l + (t / (duration || 1)) * (W - P.l - P.r);
  const y = (v) => H - P.b - (v / max) * (H - P.t - P.b);
  const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)},${y(p.pct).toFixed(1)}`).join('');
  const area = `${line}L${x(points[points.length - 1].t)},${H - P.b}L${x(points[0].t)},${H - P.b}Z`;
  const ticks = [0, Math.round(duration / 2), duration];
  const mmss = (t) => `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`;
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" dir="ltr" role="img" aria-label="نسبة المشاهدين على مدار الفيديو">
    <line x1="${P.l}" x2="${W - P.r}" y1="${y(50)}" y2="${y(50)}" stroke="var(--line)" stroke-dasharray="3 4"/>
    <line x1="${P.l}" x2="${W - P.r}" y1="${H - P.b}" y2="${H - P.b}" stroke="var(--line)"/>
    <path d="${area}" fill="var(--champagne-veil)"/>
    <path d="${line}" fill="none" stroke="var(--champagne)" stroke-width="2" stroke-linejoin="round"/>
    <text x="${P.l - 8}" y="${y(100) + 4}" text-anchor="end">100%</text>
    <text x="${P.l - 8}" y="${y(50) + 4}" text-anchor="end">50%</text>
    ${ticks.map((t) => `<text x="${x(t)}" y="${H - 6}" text-anchor="middle">${mmss(t)}</text>`).join('')}
  </svg>`;
}

function renderRetention(r) {
  const mmss = (t) => `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`;
  return `
    <div class="section-head"><h2>الاحتفاظ: الناس بتمشي فين؟</h2></div>
    <div class="grid kpis">
      ${statCard('بعد 30 ثانية', `<span class="num">${r.at_30s}%</span>`)}
      ${statCard('في نص الفيديو', `<span class="num">${r.at_half}%</span>`)}
      ${statCard('المتوسط', `<span class="num">${r.average}%</span>`)}
      ${statCard('مقارنة بفيديوهات يوتيوب بنفس الطول', `<span class="num">×${r.relative_avg}</span>`, '×1 = المتوسط')}
    </div>
    <div class="panel">${retentionChart(r.points, r.video.duration)}
      ${r.biggest_drops.length ? `<h3>أكبر نزول</h3><ul class="notes">${r.biggest_drops.map((d) => `<li>من <span class="num">${mmss(d.from)}</span> لـ <span class="num">${mmss(d.to)}</span>: نزل <span class="num">${d.drop}%</span> من المشاهدين. شوف إيه اللي بيتقال هناك.</li>`).join('')}</ul>` : ''}
    </div>`;
}

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
  const values = seoValues();
  try {
    const res = await api('/api/seo', { method: 'POST', body: values });
    $('#seo-score').innerHTML = renderSeo(res);
    updateCounters(res.counts);
    $('#ad-safety').innerHTML = renderAdSafety(await api('/api/ad-safety', { method: 'POST', body: values }));
  } catch (err) { $('#seo-score').innerHTML = errorBox(err.message); }
}, 300);

const RISK = { none: 'مفيش مشكلة', low: 'خطر قليل', medium: 'راجعها', high: 'غيّرها' };

function renderAdSafety(r) {
  return `
    <div class="panel-head"><h2>أمان الإعلانات</h2><span class="risk ${r.risk}">${RISK[r.risk]}</span></div>
    ${r.hits.length ? `<div class="checks">${r.hits.map((h) => `
      <div class="check ${r.risk === 'high' && h.field === 'العنوان' ? 'fail' : 'warn'}"><span class="mark"></span>
        <span>«${esc(h.word)}» في ${esc(h.field)}</span><span class="tip">${esc(h.category)}</span></div>`).join('')}</div>
      <p class="muted small">${esc(r.note)}</p>`
      : '<p class="muted small">مفيش كلمات معروف إنها بتقلل الإعلانات.</p>'}`;
}

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

let tagLists = [];

async function loadTagLists() {
  try { tagLists = await api('/api/taglists'); } catch { return; }
  $('#taglist-select').innerHTML = '<option value="">قوايم التاجز المحفوظة</option>'
    + tagLists.map((l) => `<option value="${esc(l.name)}">${esc(l.name)} (${l.tags.length})</option>`).join('');
}

function setTags(tags) {
  seoForm.tags.value = tags.join(', ');
  scoreSeo();
}

$('#tags-sort').addEventListener('click', async () => {
  const { tags, keyword } = seoValues();
  setTags(await api('/api/tags/sort', { method: 'POST', body: { tags, keyword } }));
  toast('اترتبت: الكلمة المستهدفة الأول');
});

$('#taglist-add').addEventListener('click', () => {
  const list = tagLists.find((l) => l.name === $('#taglist-select').value);
  if (!list) return toast('اختار قايمة الأول');
  setTags([...seoValues().tags, ...list.tags]);
});

$('#taglist-save').addEventListener('click', async () => {
  const { tags } = seoValues();
  if (!tags.length) return toast('مفيش تاجز تتحفظ');
  const name = $('#taglist-select').value || `قايمة ${new Date().toLocaleDateString('en-GB')}`;
  tagLists = await api('/api/taglists', { method: 'POST', body: { name, tags } });
  await loadTagLists();
  $('#taglist-select').value = name;
  toast(`اتحفظت في «${name}»`);
});

// ---------- competitors ----------
async function loadScorecard() {
  const box = $('#scorecard');
  try {
    const { rows, has_me } = await api('/api/scorecard');
    const cell = (r, key, val) => `${val}${r.ranks?.[key] ? `<span class="rank num">#${r.ranks[key]}</span>` : ''}`;
    box.innerHTML = (has_me ? '' : '<p class="muted small">حط لينك قناتك في الإعدادات عشان تظهر في المقارنة.</p>') + `
      <div class="table-wrap"><table>
        <thead><tr><th>القناة</th><th>المشتركين</th><th>زيادة المشتركين</th><th>المعتاد للفيديو</th><th>فيديوهات آخر 30 يوم</th><th>التفاعل</th><th>مشاهدات ÷ مشتركين</th><th>فرقعات آخر 90 يوم</th></tr></thead>
        <tbody>${rows.map((r) => `<tr class="${r.is_me ? 'me' : ''}">
          <td><div class="vid"><img src="${esc(r.thumbnail)}" alt="" style="width:32px;height:32px;border-radius:50%"><div class="t">${esc(r.title)}${r.is_me ? ' (إنت)' : ''}</div></div></td>
          <td>${cell(r, 'subs', num(r.subs))}</td>
          <td>${r.subs_growth == null ? '<span class="muted small">بعد كام يوم</span>' : cell(r, 'subs_growth', `<span class="num">${r.subs_growth >= 0 ? '+' : ''}${fmt(r.subs_growth)}</span>`)}</td>
          <td>${cell(r, 'median_views', num(r.median_views))}</td>
          <td>${cell(r, 'uploads_30d', `<span class="num">${r.uploads_30d}</span>`)}</td>
          <td>${cell(r, 'engagement', `<span class="num">${r.engagement}%</span>`)}</td>
          <td>${r.views_per_sub == null ? '—' : cell(r, 'views_per_sub', `<span class="num">${r.views_per_sub}</span>`)}</td>
          <td>${cell(r, 'outliers_90d', `<span class="num">${r.outliers_90d}</span>`)}</td>
        </tr>`).join('')}</tbody>
      </table></div>`;
  } catch (err) { box.innerHTML = errorBox(err.message); }
}

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
    if (list.length) { loadScorecard(); loadOutliers(); loadTiming(); }
  } catch (err) { box.innerHTML = errorBox(err.message); }
}

async function loadOutliers() {
  const box = $('#out-list');
  const q = new URLSearchParams({ days: $('#out-days').value, format: $('#out-format').value, channel: $('#out-channel').value });
  try {
    const rows = await api(`/api/outliers?${q}`);
    box.innerHTML = rows.length ? table(rows, ['video', 'outlier', 'views', 'vph', 'vpd', 'growth', 'age']) : empty('مفيش فيديوهات في الفترة دي.');
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

// ---------- settings ----------
function fillSettings() {
  loadStatus().then(() => {
    const pill = (el, ok) => { el.textContent = ok ? 'متسجل' : 'مش موجود'; el.classList.toggle('ok', ok); };
    const form = $('#settings-form');
    pill($('#st-key'), status.has_key);
    pill($('#st-client'), status.has_client);
    pill($('#st-ai'), status.has_ai);
    $('#st-channel').textContent = status.my_channel.title || 'مش متحددة';
    $('#st-channel').classList.toggle('ok', !!status.my_channel.id);
    form.region.placeholder = status.region;
    form.lang.placeholder = status.lang;
    form.rpm.placeholder = status.rpm;
    form.niche_keywords.value = status.niche_keywords || '';
    form.channel_voice.value = status.channel_voice || '';
    form.thumbnail_rules.value = status.thumbnail_rules || '';
    const ed = status.editing;
    form.allow_editing.checked = ed.enabled;
    $('#st-edit').textContent = ed.can_edit ? 'شغال' : ed.enabled ? 'محتاج ربط' : 'مقفول';
    $('#st-edit').classList.toggle('ok', ed.can_edit);
    $('#st-edit-link').innerHTML = ed.enabled && !ed.can_edit
      ? (status.has_client ? '<a class="btn small primary" href="/auth/login">اربط القناة ووافق على صلاحية التعديل</a>' : '<p class="muted small">حط الـ OAuth Client ID والـ Secret الأول.</p>')
      : '';
    form.rank_max_keywords.placeholder = status.rank_max_keywords;
    form.brand_alerts.checked = status.brand_alerts;
    form.brand_query.value = status.brand_query_saved || '';
    form.brand_query.placeholder = status.brand_query || 'اسم قناتك';
  });
}

$('#settings-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const form = e.target;
  const body = Object.fromEntries(new FormData(form));
  body.allow_editing = form.allow_editing.checked;
  body.brand_alerts = form.brand_alerts.checked;
  await busy($('button[type=submit]', form), async () => {
    try {
      await api('/api/settings', { method: 'POST', body });
      $$('input', form).forEach((i) => { if (i.name !== 'niche_keywords' && i.type !== 'checkbox') i.value = ''; });
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
