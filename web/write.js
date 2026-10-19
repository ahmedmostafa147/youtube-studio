'use strict';
// "الكتابة بالـ AI": titles, description + tags, script outline, chapters from a transcript.

const writeForm = $('#write-form');
let writeTab = 'titles';
const WRITE_TABS = {
  titles: { endpoint: '/api/ai/titles', button: 'اكتب 10 عناوين', wait: 'بيكتب العناوين' },
  description: { endpoint: '/api/ai/description', button: 'اكتب الوصف والتاجز', wait: 'بيكتب الوصف' },
  script: { endpoint: '/api/ai/script', button: 'اكتب السكريبت', wait: 'بيكتب السكريبت' },
  chapters: { endpoint: '/api/ai/chapters', button: 'طلّع الـ Chapters', wait: 'بيقسّم الفيديو' },
};

onEnter.write = () => {
  if (!status.has_ai && !$('#write-result').innerHTML) {
    $('#write-result').innerHTML = `<div class="panel"><p>مفيش Claude API key في الإعدادات، فالأزرار هنا مش هتشتغل.</p>
      <p class="muted small">البديل ببلاش: من Claude Code اطلب مثلًا «اكتبلي 10 عناوين لفيديو عن ... واستخدم analyze_keyword و seo_check». الأدوات بتاعتنا متوصلة بيه.</p>
      <div><a class="btn" href="#settings">حط المفتاح</a></div></div>`;
  }
};

function setWriteTab(tab) {
  writeTab = tab;
  $$('#view-write .tab').forEach((t) => t.setAttribute('aria-selected', String(t.dataset.tab === tab)));
  $$('[data-show]', writeForm).forEach((el) => { el.hidden = !el.dataset.show.split(' ').includes(tab); });
  $('#write-go').textContent = WRITE_TABS[tab].button;
}

$$('#view-write .tab').forEach((t) => t.addEventListener('click', () => setWriteTab(t.dataset.tab)));
setWriteTab('titles');

function openWriter({ topic = '', title = '', keyword = '', notes = '', tab = 'titles' }) {
  if (topic) writeForm.topic.value = topic;
  if (title) writeForm.title.value = title;
  if (keyword) writeForm.keyword.value = keyword;
  if (notes) writeForm.notes.value = notes;
  setWriteTab(tab);
  location.hash = '#write';
}

$('#write-file').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (file) writeForm.transcript.value = await file.text();
});

writeForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = Object.fromEntries(new FormData(writeForm));
  body.minutes = +body.minutes || 8;
  const box = $('#write-result');
  await busy($('#write-go'), async () => {
    box.innerHTML = loading(WRITE_TABS[writeTab].wait);
    try {
      const d = await api(WRITE_TABS[writeTab].endpoint, { method: 'POST', body });
      box.innerHTML = RENDER_WRITE[writeTab](d, body) + `<p class="usage">التكلفة <span class="num">$${d.usage.cost_usd}</span> · <span class="num">${fmt(d.usage.input_tokens)}</span> توكن دخل · <span class="num">${fmt(d.usage.output_tokens)}</span> خرج</p>`;
      box._data = d;
    } catch (err) { box.innerHTML = errorBox(err.message); }
  });
  setWriteTab(writeTab);
});

const RENDER_WRITE = {
  titles: (d) => `<div class="panel write-out"><h2>العناوين</h2>
    <p class="muted small">مترتبة بتقييم الـ SEO للعنوان (الطول ومكان الكلمة المستهدفة).</p>
    <div>${d.titles.map((t, i) => `<div class="title-opt">
      <span class="t">${esc(t.title)}</span>
      <span class="row-inline"><span class="badge num">${t.seo_score}</span><span class="badge num">${t.length} حرف</span></span>
      <span class="why"><span class="badge">${esc(t.angle)}</span> ${esc(t.why)}</span>
      <span class="row-inline wrap" style="grid-column:1/-1">
        <button class="btn small" data-copy="${esc(t.title)}">انسخ</button>
        <button class="btn small ghost" data-use-title="${i}">استخدمه في SEO</button>
        <button class="btn small ghost" data-desc-for="${i}">اكتب وصف ليه</button>
      </span></div>`).join('')}</div></div>`,

  description: (d) => `<div class="grid two">
    <div class="panel write-out">
      <div class="panel-head"><h2>الوصف</h2><button class="btn small" data-copy="${esc(d.full_description)}">انسخ</button></div>
      <div class="pre">${esc(d.full_description)}</div>
      <div class="panel-head"><h3>التاجز</h3><button class="btn small" data-copy="${esc(d.tags.join(', '))}">انسخ الكل</button></div>
      <div class="chips">${d.tags.map((t) => `<button class="chip" data-copy="${esc(t)}">${esc(t)}</button>`).join('')}</div>
      <div><button class="btn small" id="desc-to-seo">افتحه في SEO</button></div>
    </div>
    <div class="panel">${renderSeo(d.seo)}</div></div>`,

  script: (d) => {
    const text = [`الهوك:\n${d.hook}`, `المقدمة:\n${d.intro}`,
      ...d.sections.map((s) => `${s.heading} (~${s.seconds} ثانية):\n${s.talking_points.map((p) => `- ${p}`).join('\n')}`),
      `الختام:\n${d.outro}`].join('\n\n');
    const total = d.sections.reduce((sum, s) => sum + s.seconds, 0);
    return `<div class="panel write-out">
      <div class="panel-head"><h2>السكريبت</h2><span class="row-inline"><span class="muted small">حوالي ${clock(total)}</span><button class="btn small" data-copy="${esc(text)}">انسخ الكل</button></span></div>
      <h3>الهوك (أول 15 ثانية)</h3><div class="pre">${esc(d.hook)}</div>
      <h3>المقدمة</h3><div class="pre">${esc(d.intro)}</div>
      ${d.sections.map((s) => `<h3>${esc(s.heading)} <span class="muted small num">~${s.seconds}s</span></h3>
        <ul class="notes">${s.talking_points.map((p) => `<li>${esc(p)}</li>`).join('')}</ul>`).join('')}
      <h3>الختام</h3><div class="pre">${esc(d.outro)}</div></div>`;
  },

  chapters: (d) => `<div class="panel write-out">
    <div class="panel-head"><h2>الـ Chapters</h2><button class="btn small" data-copy="${esc(d.text)}">انسخ</button></div>
    <div class="pre" dir="auto">${esc(d.text)}</div>
    <div><button class="btn small" id="chapters-to-seo">ضيفها لوصف SEO</button></div></div>`,
};

$('#write-result').addEventListener('click', (e) => {
  const d = $('#write-result')._data;
  if (!d) return;
  const use = e.target.closest('[data-use-title]');
  if (use) {
    seoForm.title.value = d.titles[+use.dataset.useTitle].title;
    if (writeForm.keyword.value) seoForm.keyword.value = writeForm.keyword.value;
    scoreSeo();
    location.hash = '#seo';
  }
  const descFor = e.target.closest('[data-desc-for]');
  if (descFor) openWriter({ title: d.titles[+descFor.dataset.descFor].title, tab: 'description' });
  if (e.target.id === 'desc-to-seo') {
    fillSeoForm({ title: writeForm.title.value, description: d.full_description, tags: d.tags }, writeForm.keyword.value);
    location.hash = '#seo';
  }
  if (e.target.id === 'chapters-to-seo') {
    const current = seoForm.description.value.trimEnd();
    seoForm.description.value = `${current}${current ? '\n\n' : ''}${d.text}`;
    scoreSeo();
    location.hash = '#seo';
  }
});
