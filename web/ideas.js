'use strict';
// "الأفكار والتنبيهات": alerts, AI daily ideas, the video planner board, and trending videos.

const STAGES = { idea: 'أفكار', writing: 'بكتب', filming: 'بصوّر', editing: 'بمنتج', published: 'اتنشر' };
const ALERT_KIND = { upload: 'فيديو جديد', takeoff: 'بيفرقع', trend: 'ترند في مجالك', brand: 'ذكر اسم قناتك', scheduled: 'تغيير مجدول', ab: 'اختبار A/B' };
let trendCategoriesLoaded = false;
let lastTrends = [];

onEnter.ideas = () => {
  loadAlerts();
  loadPlanner();
  loadDaily(false);
  loadTrends();
};

function since(ts) {
  const mins = (Date.now() / 1000 - ts) / 60;
  if (mins < 60) return `من ${Math.max(1, Math.round(mins))} دقيقة`;
  if (mins < 60 * 24) return `من ${plural(Math.round(mins / 60), 'ساعة', 'ساعات')}`;
  return ago(mins / 60 / 24);
}

// ---------- alerts ----------
async function loadAlerts() {
  const box = $('#alerts-list');
  const job = status.last_job;
  $('#alerts-meta').textContent = job?.finished ? `آخر فحص ${since(job.finished)}. البرنامج بيفحص كل ساعة وهو مفتوح.` : 'البرنامج بيفحص كل ساعة وهو مفتوح.';
  try {
    const rows = await api('/api/alerts');
    box.innerHTML = rows.length ? `<div class="alerts">${rows.map((a) => `
      <a class="alert ${a.read ? '' : 'unread'}" href="${esc(a.url)}" target="_blank" rel="noopener" data-alert="${a.id}">
        <img src="${esc(a.thumbnail)}" alt="" loading="lazy">
        <div><div class="k">${ALERT_KIND[a.kind] || esc(a.kind)} · ${since(a.created)}</div>
          <div class="t">${esc(a.title)}</div><div class="muted small">${esc(a.body)}</div></div>
      </a>`).join('')}</div>`
      : empty('مفيش تنبيهات لسه. ضيف منافسين، واكتب كلمات مجالك في الإعدادات، والتنبيهات هتيجي هنا.');
  } catch (err) { box.innerHTML = errorBox(err.message); }
}

$('#alerts-list').addEventListener('click', (e) => {
  const a = e.target.closest('[data-alert]');
  if (a) api('/api/alerts/read', { method: 'POST', body: { id: +a.dataset.alert } }).then(() => a.classList.remove('unread'));
});

$('#alerts-read').addEventListener('click', async () => {
  await api('/api/alerts/read', { method: 'POST', body: {} });
  loadAlerts();
});

$('#alerts-run').addEventListener('click', (e) => busy(e.target, async () => {
  try {
    const r = await api('/api/jobs/run', { method: 'POST' });
    toast(r.skipped ? (r.skipped === 'no API key' ? 'محتاج YouTube API key الأول' : 'فيه فحص شغال دلوقتي') : 'خلص الفحص');
    await loadStatus();
    loadAlerts();
  } catch (err) { toast(err.message); }
}));

// ---------- daily ideas ----------
function ideaActions(title, keyword) {
  return `<div class="actions">
    <button class="btn small" data-plan="${esc(title)}" data-kw="${esc(keyword || '')}">ضيفها للمخطط</button>
    ${keyword ? `<button class="btn small ghost" data-analyze="${esc(keyword)}">حلل «${esc(keyword)}»</button>` : ''}
  </div>`;
}

async function loadDaily(refresh) {
  const box = $('#daily-ideas');
  if (!status.has_ai) {
    box.innerHTML = loading('بيجمع الإشارات');
    try {
      const s = await api('/api/ideas/signals');
      const seeds = [
        ...s.competitor_outliers.map((o) => ({ title: o.title, why: `فرقع عند ${o.channel} (×${o.times_usual.toFixed(1)})` })),
        ...s.niche_trending.map((t) => ({ title: t.title, why: `في الترند (#${t.rank})` })),
      ].slice(0, 10);
      box.innerHTML = `<p class="muted small">مفيش Claude API key، فدي الإشارات الخام. اطلب من Claude Code: «اقترح أفكار فيديوهات من idea signals» عشان يحوّلها لأفكار ببلاش.</p>`
        + (seeds.length ? `<div class="idea-list">${seeds.map((i) => `<div class="idea"><span class="t">${esc(i.title)}</span><span class="muted small">${esc(i.why)}</span>${ideaActions(i.title, '')}</div>`).join('')}</div>`
          : empty('مفيش إشارات لسه. ضيف منافسين وكلمات مجالك.'));
    } catch (err) { box.innerHTML = errorBox(err.message); }
    return;
  }
  box.innerHTML = loading('بيفكر في أفكار النهارده');
  try {
    const d = await api(`/api/ideas/daily${refresh ? '?refresh=1' : ''}`);
    box.innerHTML = `<div class="idea-list">${d.ideas.map((i) => `
      <div class="idea"><span class="t">${esc(i.title)}</span>
        <span class="muted small">${esc(i.why)} <span class="badge">${esc(i.based_on)}</span></span>
        ${ideaActions(i.title, i.keyword)}</div>`).join('')}</div>
      <p class="usage">${d.cached ? 'أفكار النهارده المحفوظة' : `التكلفة $${d.usage.cost_usd}`}</p>`;
  } catch (err) { box.innerHTML = errorBox(err.message); }
}

$('#daily-refresh').addEventListener('click', (e) => busy(e.target, () => loadDaily(true)));

$('#daily-ideas').addEventListener('click', async (e) => {
  const plan = e.target.closest('[data-plan]');
  if (plan) {
    await api('/api/ideas', { method: 'POST', body: { title: plan.dataset.plan, keyword: plan.dataset.kw, source: 'daily' } });
    plan.disabled = true;
    plan.textContent = 'اتضافت';
    loadPlanner();
  }
  const kw = e.target.closest('[data-analyze]');
  if (kw) analyzeKeyword(kw.dataset.analyze);
});

// ---------- planner ----------
async function loadPlanner() {
  const box = $('#planner');
  try {
    const ideas = await api('/api/ideas');
    box.innerHTML = Object.entries(STAGES).map(([key, label]) => {
      const items = ideas.filter((i) => i.status === key);
      return `<div class="column"><h3><span>${label}</span><span class="num">${items.length}</span></h3>
        ${items.map((i) => `<div class="card" data-id="${i.id}">
          <span>${esc(i.title)}</span>
          ${i.keyword ? `<span class="kw">${esc(i.keyword)}</span>` : ''}
          <div class="actions">
            <select data-move="${i.id}" aria-label="المرحلة">${Object.entries(STAGES).map(([k, l]) => `<option value="${k}" ${k === key ? 'selected' : ''}>${l}</option>`).join('')}</select>
            <button class="btn small ghost" data-write="${i.id}" title="اكتب عناوين ووصف">اكتب</button>
            ${i.keyword ? `<button class="btn small ghost" data-analyze="${esc(i.keyword)}">حلل</button>` : ''}
            <button class="btn small ghost" data-del="${i.id}" title="امسح">✕</button>
          </div></div>`).join('')}
      </div>`;
    }).join('');
    box._ideas = ideas;
  } catch (err) { box.innerHTML = errorBox(err.message); }
}

$('#idea-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const title = $('#idea-title').value.trim();
  if (!title) return;
  try {
    await api('/api/ideas', { method: 'POST', body: { title, keyword: $('#idea-keyword').value } });
    $('#idea-title').value = '';
    $('#idea-keyword').value = '';
    loadPlanner();
  } catch (err) { toast(err.message); }
});

$('#planner').addEventListener('change', async (e) => {
  const sel = e.target.closest('[data-move]');
  if (sel) {
    await api(`/api/ideas/${sel.dataset.move}`, { method: 'PATCH', body: { status: sel.value } });
    loadPlanner();
  }
});

$('#planner').addEventListener('click', async (e) => {
  const del = e.target.closest('[data-del]');
  if (del) {
    // Two-step delete: the first click asks, the second deletes.
    if (del.dataset.armed) {
      await api(`/api/ideas/${del.dataset.del}`, { method: 'DELETE' });
      loadPlanner();
    } else {
      del.dataset.armed = '1';
      del.textContent = 'متأكد؟';
    }
    return;
  }
  const write = e.target.closest('[data-write]');
  if (write) {
    const idea = $('#planner')._ideas.find((i) => i.id === +write.dataset.write);
    openWriter({ topic: idea.title, keyword: idea.keyword || '', notes: idea.notes || '' });
    return;
  }
  const kw = e.target.closest('[data-analyze]');
  if (kw) analyzeKeyword(kw.dataset.analyze);
});

// ---------- trending ----------
async function loadTrends() {
  const box = $('#trend-list');
  if (!trendCategoriesLoaded) {
    try {
      const cats = await api('/api/trends/categories');
      $('#trend-cat').innerHTML = '<option value="">كل الأقسام</option>' + cats.map((c) => `<option value="${esc(c.id)}">${esc(c.title)}</option>`).join('');
      trendCategoriesLoaded = true;
    } catch (err) { box.innerHTML = errorBox(err.message); return; }
  }
  box.innerHTML = loading();
  try {
    lastTrends = await api(`/api/trends?category=${$('#trend-cat').value}`);
    renderTrends();
  } catch (err) { box.innerHTML = errorBox(err.message); }
}

function renderTrends() {
  const nicheOnly = $('#trend-niche').checked;
  const rows = nicheOnly ? lastTrends.filter((v) => v.niche) : lastTrends;
  $('#trend-list').innerHTML = rows.length ? table(rows, [
    { h: '#', cell: (v) => `<span class="num">${v.rank}</span>` },
    'video', 'views', 'vpd', 'age',
    { h: 'مجالك', cell: (v) => (v.niche ? '<span class="yes">✓</span>' : '<span class="no">—</span>') },
  ]) : empty(nicheOnly ? 'مفيش فيديوهات في مجالك في الترند دلوقتي. اتأكد من كلمات مجالك في الإعدادات.' : 'مفيش ترند للقسم ده في بلدك.');
}

$('#trend-cat').addEventListener('change', loadTrends);
$('#trend-niche').addEventListener('change', renderTrends);
