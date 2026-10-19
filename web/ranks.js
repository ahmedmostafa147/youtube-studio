'use strict';
// "ترتيبك في البحث": tag rankings, daily rank tracking, brand alerts. Every search costs 100 quota units,
// so each control shows its cost before it runs.

const SEARCH_COST = 100;
const tagrankForm = $('#tagrank-form');

onEnter.ranks = () => { loadRanks(); renderBrand(); updateTagCost(); };

function updateTagCost() {
  const typed = tagrankForm.tags.value.split(/[,،]/).map((t) => t.trim()).filter(Boolean).length;
  const n = typed ? Math.min(typed, +tagrankForm.limit.value) : +tagrankForm.limit.value;
  $('#tagrank-cost').innerHTML = `بالكتير <span class="num">${n} × 100 = ${(n * SEARCH_COST).toLocaleString('en')}</span> وحدة`;
}

tagrankForm.addEventListener('input', updateTagCost);

tagrankForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const tags = tagrankForm.tags.value.split(/[,،]/).map((t) => t.trim()).filter(Boolean);
  const box = $('#tagrank-result');
  await busy($('button[type=submit]', tagrankForm), async () => {
    box.innerHTML = loading('بيدوّر في البحث');
    try {
      const d = await api('/api/ranks/tags', { method: 'POST', body: { url: tagrankForm.url.value, tags, limit: +tagrankForm.limit.value } });
      box.innerHTML = `<div class="vid"><img src="${esc(d.video.thumbnail)}" alt=""><div class="t">${esc(d.video.title)}</div></div>
        ${table(d.rows, [
          { h: 'الكلمة', cell: (r) => `<bdi>${esc(r.tag)}</bdi>` },
          { h: 'الترتيب', cell: (r) => rankBadge(r.rank, d.depth) },
          { h: 'الأول في البحث', cls: 'title-cell', cell: (r) => `<span class="muted small">${esc(r.leader)}</span>` },
        ])}<p class="usage">اتصرف <span class="num">${d.cost}</span> وحدة. النتايج بتختلف حسب البلد وحساب اللي بيدوّر.</p>`;
    } catch (err) { box.innerHTML = errorBox(err.message); }
  });
});

function rankBadge(rank, depth = 50) {
  if (!rank) return `<span class="muted small">مش في أول ${depth}</span>`;
  return `<span class="badge ${rank <= 10 ? 'hot' : ''} num">#${rank}</span>`;
}

function spark(history) {
  const pts = history.filter((h) => h.rank);
  if (pts.length < 2) return '';
  const W = 120, H = 28, max = Math.max(...pts.map((p) => p.rank), 10);
  const x = (i) => (i / (history.length - 1)) * W;
  const y = (r) => ((r - 1) / (max - 1)) * (H - 4) + 2; // rank 1 at the top
  const d = history.map((h, i) => (h.rank ? `${x(i).toFixed(1)},${y(h.rank).toFixed(1)}` : null)).filter(Boolean);
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" dir="ltr" role="img" aria-label="الترتيب آخر 30 يوم"><polyline points="${d.join(' ')}" fill="none" stroke="var(--champagne)" stroke-width="1.5"/></svg>`;
}

async function loadRanks(data) {
  const box = $('#ranks-list');
  try {
    const d = data || await api('/api/ranks');
    $('#ranks-cost').innerHTML = `بتتفحص مرة في اليوم وإنت فاتح البرنامج: <span class="num">${d.keywords.length}</span> كلمة × 100 = <b class="num">${d.daily_cost.toLocaleString('en')}</b> وحدة في اليوم. الحد <span class="num">${d.max}</span> كلمات (تقدر تغيّره من <a href="#settings">الإعدادات</a>). من غير فيديو معين، بيدوّر على أعلى فيديو من قناتك في أول ${d.depth} نتيجة.`;
    box.innerHTML = d.keywords.length ? table(d.keywords, [
      { h: 'الكلمة', cell: (r) => `<bdi>${esc(r.keyword)}</bdi>${r.video_id ? '<div class="muted small">فيديو معين</div>' : ''}` },
      { h: 'الترتيب النهارده', cell: (r) => (r.latest ? rankBadge(r.latest.rank, d.depth) : '<span class="muted small">لسه متفحصتش</span>') },
      { h: 'التغيير', cell: (r) => (r.change == null ? '—' : `<span class="delta ${r.change >= 0 ? 'up' : 'down'} num">${r.change > 0 ? '▲' : r.change < 0 ? '▼' : ''}${Math.abs(r.change)}</span>`) },
      { h: 'آخر 30 يوم', cell: (r) => spark(r.history) || '<span class="muted small">—</span>' },
      { h: 'الفيديو', cls: 'title-cell', cell: (r) => (r.latest?.video_id ? `<a href="https://www.youtube.com/watch?v=${esc(r.latest.video_id)}" target="_blank" rel="noopener">${esc(r.latest.video_title)}</a>` : '—') },
      { h: '', cell: (r) => `<button class="btn ghost small" data-unrank="${esc(r.keyword)}" title="بطّل تتابعها">✕</button>` },
    ]) : empty('ضيف الكلمات اللي عاوز تعرف ترتيبك فيها كل يوم.');
  } catch (err) { box.innerHTML = errorBox(err.message); }
}

$('#ranks-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = e.target;
  try {
    await loadRanks(await api('/api/ranks', { method: 'POST', body: { keyword: f.keyword.value, url: f.url.value } }));
    f.reset();
    toast('هتتفحص في الفحص الجاي، أو دوس «افحص دلوقتي»');
  } catch (err) { toast(err.message); }
});

$('#ranks-list').addEventListener('click', async (e) => {
  const btn = e.target.closest('[data-unrank]');
  if (!btn || !confirm(`تبطّل تتابع «${btn.dataset.unrank}» وتمسح تاريخها؟`)) return;
  loadRanks(await api(`/api/ranks/${encodeURIComponent(btn.dataset.unrank)}`, { method: 'DELETE' }));
});

$('#ranks-check').addEventListener('click', (e) => busy(e.target, async () => {
  try {
    const d = await api('/api/ranks/check', { method: 'POST' });
    toast(d.checked ? `اتفحصت ${d.checked} كلمة (${d.checked * SEARCH_COST} وحدة)` : 'كل الكلمات اتفحصت النهارده بالفعل');
    loadRanks(d);
  } catch (err) { toast(err.message); }
}));

function renderBrand() {
  $('#brand-panel').innerHTML = `
    <p>${status.brand_alerts ? `شغالة: مرة في اليوم بيدوّر على <b>«${esc(status.brand_query || '')}»</b> في الفيديوهات الجديدة (آخر 3 أيام) من قنوات تانية، واللي يلاقيه بيظهر في <a href="#ideas">التنبيهات</a>. <span class="num">100</span> وحدة في اليوم.`
      : 'مقفولة. فعّلها من <a href="#settings">الإعدادات</a> عشان تعرف لما حد يذكر اسم قناتك في فيديو (مرة في اليوم = 100 وحدة).'}</p>`;
}

$('#brand-check').addEventListener('click', (e) => busy(e.target, async () => {
  try {
    const d = await api('/api/brand/check', { method: 'POST' });
    toast(d.found ? `لقيت ${d.found} فيديو جديد بيذكر «${d.query}». شوف التنبيهات.` : `مفيش فيديوهات جديدة بتذكر «${d.query}»`);
  } catch (err) { toast(err.message); }
}));
