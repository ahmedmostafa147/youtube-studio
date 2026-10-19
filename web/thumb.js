'use strict';
// "الثمبنيل": preview your thumbnail at real sizes and next to competitors, plus an optional AI review.

let thumbData = '';
let thumbMode = 'home';
let thumbContext = null;

onEnter.thumb = () => {
  if (!thumbContext) loadThumbContext();
};

function readImage(file) {
  // Downscale big images so the upload stays small; YouTube thumbnails are 1280x720 anyway.
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const scale = Math.min(1, 1280 / img.width);
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(img.src);
      resolve({ url: canvas.toDataURL('image/jpeg', 0.9), canvas, ratio: img.width / img.height });
    };
    img.onerror = () => reject(new Error('مش قادر أقرا الصورة دي.'));
    img.src = URL.createObjectURL(file);
  });
}

function imageStats(canvas) {
  const small = document.createElement('canvas');
  small.width = 160;
  small.height = 90;
  const ctx = small.getContext('2d');
  ctx.drawImage(canvas, 0, 0, 160, 90);
  const px = ctx.getImageData(0, 0, 160, 90).data;
  const lum = [];
  for (let i = 0; i < px.length; i += 4) lum.push(0.2126 * px[i] + 0.7152 * px[i + 1] + 0.0722 * px[i + 2]);
  const mean = lum.reduce((a, b) => a + b, 0) / lum.length;
  const std = Math.sqrt(lum.reduce((a, b) => a + (b - mean) ** 2, 0) / lum.length);
  return { brightness: Math.round((mean / 255) * 100), contrast: Math.round(std) };
}

$('#thumb-file').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  try {
    const { url, canvas, ratio } = await readImage(file);
    thumbData = url;
    $('#thumb-sizes').innerHTML = [[360, 'الصفحة الرئيسية'], [246, 'نتايج البحث على الموبايل'], [168, 'الفيديوهات المقترحة'], [120, 'أصغر حجم']]
      .map(([w, label]) => `<figure><img src="${url}" width="${w}" height="${Math.round(w * 9 / 16)}" alt="" style="object-fit:cover"><figcaption>${label} · <span class="num">${w}px</span></figcaption></figure>`).join('');
    const s = imageStats(canvas);
    const ratioOk = Math.abs(ratio - 16 / 9) < 0.02;
    $('#thumb-stats').innerHTML = `<div class="checks">
      <div class="check ${ratioOk ? 'pass' : 'fail'}"><span class="mark"></span><span>المقاس ${ratioOk ? '16:9' : 'مش 16:9'}</span>${ratioOk ? '' : '<span class="tip">يوتيوب هيحط حواف سودا. خليها 1280×720.</span>'}</div>
      <div class="check ${s.contrast >= 55 ? 'pass' : s.contrast >= 40 ? 'warn' : 'fail'}"><span class="mark"></span><span>التباين: <span class="num">${s.contrast}</span></span>${s.contrast < 55 ? '<span class="tip">الصورة باهتة شوية. فرق أكبر بين الفاتح والغامق بيخليها تبان وهي صغيرة.</span>' : ''}</div>
      <div class="check ${s.brightness >= 15 && s.brightness <= 85 ? 'pass' : 'warn'}"><span class="mark"></span><span>السطوع: <span class="num">${s.brightness}%</span></span>${s.brightness < 15 ? '<span class="tip">غامقة جدًا، ممكن تضيع في الوضع الغامق.</span>' : s.brightness > 85 ? '<span class="tip">فاتحة جدًا، ممكن تضيع في الوضع الفاتح.</span>' : ''}</div>
    </div><p class="muted small">بص على أصغر حجم: لو الكلام مش مقروء هناك، كبّره أو قلّله.</p>`;
    renderThumbPreview();
  } catch (err) { toast(err.message); }
});

async function loadThumbContext() {
  const kw = $('#thumb-keyword').value.trim();
  try {
    thumbContext = await api(`/api/thumbnail/context?keyword=${encodeURIComponent(kw)}`);
    renderThumbPreview();
  } catch (err) { $('#thumb-preview').innerHTML = errorBox(err.message); }
}

function myCard() {
  return {
    mine: true,
    thumbnail: thumbData,
    title: $('#thumb-title').value || 'عنوان الفيديو بتاعك',
    channel_title: status.my_channel?.title || 'قناتك',
  };
}

function ytCard(v) {
  return `<div class="yt-card ${v.mine ? 'mine' : ''}">
    <img src="${esc(v.thumbnail)}" alt="" loading="lazy">
    <div><div class="t">${esc(v.title)}</div>
      <div class="m">${esc(v.channel_title)}${v.mine ? ' · فيديوك' : ` · ${fmt(v.views)} مشاهدة · ${ago(v.age_days)}`}</div></div>
  </div>`;
}

function renderThumbPreview() {
  const box = $('#thumb-preview');
  if (!thumbData) { box.innerHTML = empty('ارفع الثمبنيل الأول.'); return; }
  if (!thumbContext) { box.innerHTML = loading(); return; }
  if (thumbMode === 'home') {
    const others = thumbContext.home;
    if (!others.length) { box.innerHTML = empty('ضيف منافسين الأول عشان تشوف الثمبنيل جنب فيديوهاتهم.'); return; }
    const cards = [...others.slice(0, 1), myCard(), ...others.slice(1, 8)];
    box.innerHTML = `<div class="yt-home">${cards.map(ytCard).join('')}</div>`;
  } else {
    const others = thumbContext.search;
    if (!others.length) {
      box.innerHTML = empty('حلل الكلمة المستهدفة في صفحة «الكلمات المفتاحية» الأول (حوالي 102 وحدة)، وبعدين ارجع هنا عشان تشوف نتايج البحث الحقيقية.');
      return;
    }
    const cards = [...others.slice(0, 2), myCard(), ...others.slice(2, 6)];
    box.innerHTML = `<div class="yt-search">${cards.map(ytCard).join('')}</div>`;
  }
}

$('#thumb-tabs').addEventListener('click', (e) => {
  const tab = e.target.closest('[data-mode]');
  if (!tab) return;
  thumbMode = tab.dataset.mode;
  $$('#thumb-tabs .tab').forEach((t) => t.setAttribute('aria-selected', String(t === tab)));
  renderThumbPreview();
});

$('#thumb-preview-btn').addEventListener('click', () => loadThumbContext());
$('#thumb-title').addEventListener('input', debounce(renderThumbPreview, 200));

$('#thumb-review-btn').addEventListener('click', (e) => busy(e.target, async () => {
  const box = $('#thumb-review');
  if (!thumbData) { toast('ارفع الصورة الأول'); return; }
  box.innerHTML = '<h2>تقييم الـ AI</h2>' + loading('بيبص على الصورة');
  try {
    const r = await api('/api/thumbnail/review', { method: 'POST', body: { image: thumbData, title: $('#thumb-title').value, keyword: $('#thumb-keyword').value } });
    const t = tone(r.score);
    const list = (title, items) => (items.length ? `<h3>${title}</h3><ul class="notes">${items.map((i) => `<li>${esc(i)}</li>`).join('')}</ul>` : '');
    box.innerHTML = `
      <div class="panel-head"><h2>تقييم الـ AI</h2><span class="usage num">$${r.usage.cost_usd}</span></div>
      <div class="score-big ${t} num">${r.score}</div>
      <div class="meter ${t === 'bad' ? 'rust' : ''}"><span style="width:${r.score}%"></span></div>
      <p>${esc(r.verdict)}</p>
      <div class="muted small">مقروءة وهي صغيرة: ${r.readable_small ? 'أيوه' : 'لأ'} · كلام على الصورة: <span class="num">${r.words_on_image}</span> كلمة · نقطة التركيز: ${esc(r.focal_point)}</div>
      ${list('كويس', r.strengths)}${list('مشاكل', r.issues)}${list('جرّب', r.suggestions)}`;
  } catch (err) { box.innerHTML = '<h2>تقييم الـ AI</h2>' + errorBox(err.message); }
}));
