'use strict';
// "تعديل القناة": bulk edits, upload profiles, translations, scheduled changes, A/B rotation, playlists, replies, history.
// Every write starts from a free preview; nothing changes on YouTube until the user ticks videos and presses apply.

const editPane = $('#edit-pane');
const WRITE_COST = 50;
let editTab = 'bulk';
let categories = null;

onEnter.edit = () => { loadStatus().then(() => { renderGate(); setEditTab(editTab); }); };

const units = (n) => `<span class="num">${(n * WRITE_COST).toLocaleString('en')}</span> وحدة`;
const thumbUrl = (name) => (name ? `/api/thumbs/${encodeURIComponent(name)}` : '');
const ytLink = (id) => `https://www.youtube.com/watch?v=${esc(id)}`;

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

async function readThumb(input) {
  const file = input.files[0];
  if (!file) return null;
  if (file.size > 2_000_000) throw new Error('يوتيوب مش بيقبل ثمبنيل أكبر من 2MB.');
  return fileToDataUrl(file);
}

function renderGate() {
  const ed = status.editing;
  const box = $('#edit-gate');
  if (!status.connected) {
    box.innerHTML = `<div class="panel gate"><p>اربط قناتك الأول من صفحة «قناتي». المعاينات بتشتغل بصلاحية القراءة، والتطبيق محتاج صلاحية التعديل.</p>
      <div><a class="btn primary" href="#me">روح لقناتي</a></div></div>`;
  } else if (!ed.enabled) {
    box.innerHTML = `<div class="panel gate"><p>التعديل مقفول. تقدر تعمل معاينة لأي تغيير، بس عشان تطبّقه لازم تفعّل التعديل من الإعدادات وتربط القناة تاني.</p>
      <div><a class="btn" href="#settings">فعّل التعديل</a></div></div>`;
  } else if (!ed.can_edit) {
    box.innerHTML = `<div class="panel gate"><p>التعديل متفعّل، بس الربط الحالي قراءة بس. اربط القناة تاني ووافق على صلاحية التعديل.</p>
      <div><a class="btn primary" href="/auth/login">اربط بصلاحية التعديل</a></div></div>`;
  } else {
    box.innerHTML = `<p class="muted small gate-ok">التعديل شغال · الباقي من الـ quota النهارده <span class="num">${ed.quota_left.toLocaleString('en')}</span> وحدة (يعني حوالي <span class="num">${Math.floor(ed.quota_left / WRITE_COST)}</span> تعديل).</p>`;
  }
}

function setEditTab(tab) {
  editTab = tab;
  $$('#edit-tabs .tab').forEach((t) => t.setAttribute('aria-selected', String(t.dataset.tab === tab)));
  editPane.innerHTML = EDIT_TABS[tab].html();
  EDIT_TABS[tab].init?.();
}

$$('#edit-tabs .tab').forEach((t) => t.addEventListener('click', () => setEditTab(t.dataset.tab)));

function results(r) {
  const label = { done: 'اتعمل', skipped: 'اتساب', failed: 'فشل' };
  return `<div class="checks">${r.results.map((x) => `
    <div class="check ${x.status === 'done' ? 'pass' : x.status === 'failed' ? 'fail' : 'warn'}"><span class="mark"></span>
      <span>${esc(x.title || x.id)} — ${label[x.status]}</span>${x.message ? `<span class="tip">${esc(x.message)}</span>` : ''}</div>`).join('')}</div>`;
}

function diffBlocks(excerpts) {
  return excerpts.map((e) => `<div class="diff"><div class="del" dir="auto">${esc(e.before) || '<span class="muted">(فاضي)</span>'}</div>
    <div class="ins" dir="auto">${esc(e.after)}</div></div>`).join('');
}

function needEdit() {
  if (status.editing.can_edit) return true;
  toast('فعّل التعديل من الإعدادات واربط القناة تاني الأول');
  return false;
}

// ---------- bulk ----------
let bulkLast = null;

const EDIT_TABS = {};

EDIT_TABS.bulk = {
  html: () => `
    <form class="panel" id="bulk-form" autocomplete="off">
      <p class="muted small">دوّر واستبدل في كل فيديوهاتك مرة واحدة، أو ضيف سطر في أول أو آخر الوصف (لينك جديد، سنة، سوشيال). المعاينة بتاخد حوالي وحدتين لكل 50 فيديو.</p>
      <div class="row-inline wrap">
        <label>في <select name="field"><option value="description">الوصف</option><option value="title">العنوان</option></select></label>
        <label>العملية <select name="mode">
          <option value="replace">دوّر واستبدل</option>
          <option value="append">ضيف في الآخر</option>
          <option value="prepend">ضيف في الأول</option></select></label>
        <label class="check-inline"><input type="checkbox" name="case"> فرق بين الحروف الكبيرة والصغيرة</label>
      </div>
      <label data-mode="replace">دوّر على <input name="find" placeholder="مثلًا: لينك الكورس القديم"></label>
      <label><span id="bulk-replace-label">استبدله بـ</span> <textarea name="replace" rows="3" placeholder="سيبها فاضية عشان تمسح الكلام"></textarea></label>
      <label>فيديوهات معينة (اختياري، لينك في كل سطر) <textarea name="videos" rows="2" placeholder="سيبها فاضية عشان يدوّر في كل فيديوهاتك"></textarea></label>
      <div><button class="btn primary" type="submit">اعرض المعاينة</button></div>
    </form>
    <div id="bulk-result"></div>`,
  init() {
    const form = $('#bulk-form');
    const sync = () => {
      const replace = form.mode.value === 'replace';
      $('[data-mode="replace"]', form).hidden = !replace;
      $('#bulk-replace-label').textContent = replace ? 'استبدله بـ' : 'الكلام اللي هيتضاف';
      form.replace.placeholder = replace ? 'سيبها فاضية عشان تمسح الكلام' : 'مثلًا: كورس Claude Code الجديد: https://...';
    };
    form.mode.addEventListener('change', sync);
    sync();
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const body = bulkBody(form);
      const box = $('#bulk-result');
      await busy($('button[type=submit]', form), async () => {
        box.innerHTML = loading('بيدوّر في فيديوهاتك');
        try {
          bulkLast = { body, data: await api('/api/bulk/preview', { method: 'POST', body }) };
          box.innerHTML = renderBulk(bulkLast.data);
        } catch (err) { box.innerHTML = errorBox(err.message); }
      });
    });
    $('#bulk-result').addEventListener('change', updateBulkCount);
    $('#bulk-result').addEventListener('click', async (e) => {
      if (e.target.id === 'bulk-all') {
        $$('.bulk-pick:not(:disabled)').forEach((c) => { c.checked = e.target.dataset.on !== '1'; });
        e.target.dataset.on = e.target.dataset.on === '1' ? '' : '1';
        updateBulkCount();
      }
      if (e.target.id === 'bulk-apply') applyBulk(e.target);
    });
  },
};

function bulkBody(form) {
  return {
    field: form.field.value, mode: form.mode.value, find: form.find.value, replace: form.replace.value,
    case: form.case.checked, videos: form.videos.value.split('\n').map((l) => l.trim()).filter(Boolean),
  };
}

function renderBulk(d) {
  if (!d.matches.length) return empty(`مفيش ولا فيديو هيتغيّر (اتفحص ${d.checked} فيديو).`);
  return `<div class="panel">
    <div class="panel-head"><h2>هيتغيّر ${d.matches.length} فيديو من ${d.checked}</h2>
      <button class="btn small" type="button" id="bulk-all">اختار الكل</button></div>
    <p class="muted small">اختار الفيديوهات اللي عاوز تطبّق عليها بنفسك. الأحمر هيتشال والدهبي هيتحط. كل فيديو بيتقري تاني قبل التعديل مباشرة.</p>
    <div class="pick-list">${d.matches.map((m) => `
      <label class="pick">
        <input type="checkbox" class="bulk-pick" value="${esc(m.id)}" ${m.problems.length ? 'disabled' : ''}>
        <img src="${esc(m.thumbnail)}" alt="" loading="lazy">
        <div class="pick-body">
          <a href="${ytLink(m.id)}" target="_blank" rel="noopener" class="t">${esc(m.title)}</a>
          <div class="muted small">${m.count > 1 ? `${m.count} أماكن · ` : ''}${m.privacy ? esc(m.privacy) : ''}</div>
          ${diffBlocks(m.excerpts)}
          ${m.problems.map((p) => `<div class="error-inline">${esc(p)}</div>`).join('')}
        </div>
      </label>`).join('')}</div>
    <div class="row-inline wrap apply-bar">
      <button class="btn primary" type="button" id="bulk-apply" disabled>طبّق على المختار</button>
      <span class="muted small" id="bulk-count"></span>
    </div>
    <div id="bulk-done"></div>
  </div>`;
}

function updateBulkCount() {
  const n = $$('.bulk-pick:checked').length;
  const btn = $('#bulk-apply');
  if (!btn) return;
  btn.disabled = !n;
  btn.textContent = n ? `طبّق على ${n} فيديو` : 'طبّق على المختار';
  $('#bulk-count').innerHTML = n ? `هياخد ${units(n)} من الـ quota` : 'اختار فيديو واحد على الأقل';
}

async function applyBulk(btn) {
  if (!needEdit()) return;
  const ids = $$('.bulk-pick:checked').map((c) => c.value);
  if (!ids.length || !confirm(`هتعدّل ${ids.length} فيديو على يوتيوب (${ids.length * WRITE_COST} وحدة). متأكد؟`)) return;
  await busy(btn, async () => {
    try {
      const r = await api('/api/bulk/apply', { method: 'POST', body: { ...bulkLast.body, videos: ids } });
      $('#bulk-done').innerHTML = `<h3>اتعدّل ${r.done} فيديو</h3>${results(r)}`;
      toast(`اتعدّل ${r.done} فيديو`);
    } catch (err) { $('#bulk-done').innerHTML = errorBox(err.message); }
  });
}

// ---------- profiles ----------
let profileList = [];

EDIT_TABS.profiles = {
  html: () => `
    <div class="grid two">
      <form class="panel" id="profile-form" autocomplete="off">
        <h2>قالب جديد أو تعديل قالب</h2>
        <p class="muted small">قالب بعنوان ووصف وتاجز ثابتين تطبّقه على أي فيديو جديد. استخدم <code>{title}</code> للعنوان الحالي، <code>{description}</code> للوصف الحالي، <code>{date}</code> لتاريخ النهارده. أي خانة فاضية الفيديو بيفضل زي ما هو فيها.</p>
        <label>اسم القالب <input name="name" placeholder="مثلًا: شروحات الأدوات"></label>
        <label>العنوان <input name="title" placeholder="{title} | شرح بالعربي"></label>
        <label>الوصف <textarea name="description" rows="6" placeholder="{description}&#10;&#10;تابعني: ..."></textarea></label>
        <label>التاجز (افصل بفاصلة) <textarea name="tags" rows="2"></textarea></label>
        <div class="row-inline wrap">
          <label>التاجز <select name="tags_mode"><option value="append">تتضاف للموجودة</option><option value="replace">تحل محلها</option></select></label>
          <label>القسم <select name="category_id"><option value="">زي ما هو</option></select></label>
        </div>
        <div><button class="btn primary" type="submit">احفظ القالب</button></div>
      </form>
      <div class="panel">
        <h2>طبّق قالب على فيديو</h2>
        <div id="profile-list"></div>
        <form class="row-inline wrap" id="profile-apply-form" autocomplete="off">
          <label class="grow">القالب <select name="name"></select></label>
          <label class="grow">لينك الفيديو <input name="url" placeholder="https://youtu.be/..."></label>
          <button class="btn" type="submit">معاينة</button>
        </form>
        <div id="profile-preview"></div>
      </div>
    </div>`,
  async init() {
    const form = $('#profile-form');
    loadProfiles();
    try {
      categories = categories || await api('/api/trends/categories');
      form.category_id.innerHTML += categories.map((c) => `<option value="${esc(c.id)}">${esc(c.title)}</option>`).join('');
    } catch { /* categories are optional */ }
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const body = Object.fromEntries(new FormData(form));
      body.tags = body.tags.split(/[,،\n]/).map((t) => t.trim()).filter(Boolean);
      try {
        profileList = await api('/api/profiles', { method: 'POST', body });
        renderProfiles();
        toast('اتحفظ القالب');
      } catch (err) { toast(err.message); }
    });
    $('#profile-list').addEventListener('click', async (e) => {
      const edit = e.target.closest('[data-edit-profile]');
      const del = e.target.closest('[data-del-profile]');
      if (edit) {
        const p = profileList.find((x) => x.name === edit.dataset.editProfile);
        Object.entries({ name: p.name, title: p.title, description: p.description, tags: p.tags.join(', '), tags_mode: p.tags_mode, category_id: p.category_id })
          .forEach(([k, v]) => { form[k].value = v || ''; });
      }
      if (del && confirm(`تمسح القالب «${del.dataset.delProfile}»؟`)) {
        profileList = await api(`/api/profiles/${encodeURIComponent(del.dataset.delProfile)}`, { method: 'DELETE' });
        renderProfiles();
      }
    });
    $('#profile-apply-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const body = Object.fromEntries(new FormData(e.target));
      const box = $('#profile-preview');
      box.innerHTML = loading();
      try {
        const d = await api('/api/profiles/preview', { method: 'POST', body });
        box.innerHTML = renderProfilePreview(d);
        box._body = body;
      } catch (err) { box.innerHTML = errorBox(err.message); }
    });
    $('#profile-preview').addEventListener('click', async (e) => {
      if (e.target.id !== 'profile-apply' || !needEdit()) return;
      if (!confirm(`تطبّق القالب على الفيديو ده؟ (${WRITE_COST} وحدة)`)) return;
      await busy(e.target, async () => {
        try {
          await api('/api/profiles/apply', { method: 'POST', body: $('#profile-preview')._body });
          toast('اتطبّق القالب');
          e.target.replaceWith(Object.assign(document.createElement('p'), { className: 'muted small', textContent: 'اتطبّق. تقدر ترجّعه من «السجل».' }));
        } catch (err) { toast(err.message); }
      });
    });
  },
};

async function loadProfiles() {
  try { profileList = await api('/api/profiles'); } catch { profileList = []; }
  renderProfiles();
}

function renderProfiles() {
  $('#profile-list').innerHTML = profileList.length ? `<div class="chips">${profileList.map((p) => `
    <span class="chip">${esc(p.name)}
      <button class="btn ghost small" type="button" data-edit-profile="${esc(p.name)}" title="عدّل">✎</button>
      <button class="btn ghost small" type="button" data-del-profile="${esc(p.name)}" title="امسح">✕</button></span>`).join('')}</div>`
    : '<p class="muted small">لسه معملتش قوالب.</p>';
  const select = $('#profile-apply-form select[name=name]');
  if (select) select.innerHTML = profileList.map((p) => `<option>${esc(p.name)}</option>`).join('');
}

function beforeAfter(label, before, after) {
  const changed = JSON.stringify(before) !== JSON.stringify(after);
  const show = (v) => esc(Array.isArray(v) ? v.join(', ') : v ?? '');
  return `<div class="ba ${changed ? 'changed' : ''}"><h3>${label} ${changed ? '<span class="badge hot">هيتغيّر</span>' : '<span class="badge">زي ما هو</span>'}</h3>
    ${changed ? `<div class="diff"><div class="del" dir="auto">${show(before) || '<span class="muted">(فاضي)</span>'}</div><div class="ins" dir="auto">${show(after)}</div></div>` : ''}</div>`;
}

function renderProfilePreview(d) {
  const v = d.video;
  return `<div class="vid"><img src="${esc(v.thumbnail)}" alt=""><div class="t">${esc(v.title)}</div></div>
    ${beforeAfter('العنوان', v.title, d.after.title)}
    ${beforeAfter('الوصف', v.description, d.after.description)}
    ${beforeAfter('التاجز', v.tags, d.after.tags)}
    ${beforeAfter('القسم', v.category_id, d.after.category_id)}
    ${d.problems.map((p) => `<div class="error-inline">${esc(p)}</div>`).join('')}
    ${d.changed && !d.problems.length ? `<div><button class="btn primary" type="button" id="profile-apply">طبّق على يوتيوب (${WRITE_COST} وحدة)</button></div>`
      : d.changed ? '' : '<p class="muted small">القالب مش هيغيّر حاجة في الفيديو ده.</p>'}`;
}

// ---------- translations ----------
let languages = null;
const langNames = new Intl.DisplayNames(['ar'], { type: 'language' });
const langName = (c) => { try { return langNames.of(c); } catch { return c; } };

EDIT_TABS.translate = {
  html: () => `
    <form class="panel" id="tr-form" autocomplete="off">
      <p class="muted small">ترجمة العنوان والوصف بتظهر للمشاهدين اللي لغة يوتيوب عندهم مختلفة، وبتساعد في البحث بلغات تانية. الترجمة بالـ AI (بسنتات) أو اكتبها بنفسك، وبعدين احفظها مرة واحدة (${WRITE_COST} وحدة).</p>
      <div class="row-inline wrap">
        <label class="grow">لينك الفيديو <input name="url" placeholder="https://youtu.be/..."></label>
        <button class="btn" type="button" id="tr-load">حمّل الفيديو</button>
      </div>
      <div class="chips" id="tr-langs"></div>
      <div class="row-inline wrap">
        <button class="btn primary" type="submit">ترجم بالـ AI</button>
        <span class="muted small">${status.has_ai ? '' : 'محتاج Claude API key من الإعدادات، أو اطلب الترجمة من Claude Code (أداة save_localizations).'}</span>
      </div>
    </form>
    <div id="tr-result"></div>`,
  async init() {
    languages = languages || await api('/api/translate/languages').catch(() => ({}));
    const pick = ['en', 'fr'];
    $('#tr-langs').innerHTML = Object.keys(languages).filter((c) => c !== status.lang).map((c) => `
      <label class="chip check-inline"><input type="checkbox" value="${c}" ${pick.includes(c) ? 'checked' : ''}> ${esc(langName(c))} <span class="count">${c}</span></label>`).join('');
    const form = $('#tr-form');
    $('#tr-load').addEventListener('click', (e) => busy(e.target, async () => {
      const box = $('#tr-result');
      try {
        const v = await api(`/api/edit/video?url=${encodeURIComponent(form.url.value)}`);
        box.innerHTML = renderTranslations(v, v.localizations);
      } catch (err) { box.innerHTML = errorBox(err.message); }
    }));
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const langs = $$('#tr-langs input:checked').map((i) => i.value);
      const box = $('#tr-result');
      await busy($('button[type=submit]', form), async () => {
        box.innerHTML = loading('بيترجم');
        try {
          const d = await api('/api/translate', { method: 'POST', body: { url: form.url.value, languages: langs } });
          box.innerHTML = renderTranslations(d.video, { ...d.video.localizations, ...d.translations })
            + `<p class="usage">التكلفة <span class="num">$${d.usage.cost_usd}</span></p>`;
        } catch (err) { box.innerHTML = errorBox(err.message); }
      });
    });
    $('#tr-result').addEventListener('click', async (e) => {
      if (e.target.id !== 'tr-save' || !needEdit()) return;
      const translations = {};
      $$('.tr-lang').forEach((el) => {
        const title = $('input', el).value.trim();
        if (title) translations[el.dataset.lang] = { title, description: $('textarea', el).value };
      });
      if (!Object.keys(translations).length) return toast('مفيش ترجمات تتحفظ');
      if (!confirm(`تحفظ ${Object.keys(translations).length} ترجمة على الفيديو؟ (${WRITE_COST} وحدة)`)) return;
      await busy(e.target, async () => {
        try {
          const r = await api('/api/localizations', { method: 'POST', body: { url: $('#tr-form').url.value, translations } });
          toast(`اتحفظت: ${r.languages.join(', ')}`);
        } catch (err) { toast(err.message); }
      });
    });
  },
};

function renderTranslations(v, loc) {
  const langs = Object.keys(loc || {});
  return `<div class="panel">
    <div class="vid"><img src="${esc(v.thumbnail)}" alt=""><div><div class="t">${esc(v.title)}</div>
      <div class="c">لغة الفيديو: ${esc(v.default_language || 'مش متحددة (هتتحط ' + status.lang + ')')}</div></div></div>
    ${langs.length ? langs.map((l) => `<div class="tr-lang" data-lang="${esc(l)}">
      <h3>${esc(langName(l))} <span class="muted small">${esc(l)}</span></h3>
      <input value="${esc(loc[l].title)}" maxlength="100" dir="auto">
      <textarea rows="5" dir="auto">${esc(loc[l].description)}</textarea></div>`).join('')
      : '<p class="muted small">مفيش ترجمات لسه. اختار لغات ودوس «ترجم بالـ AI».</p>'}
    ${langs.length ? `<div><button class="btn primary" type="button" id="tr-save">احفظ الترجمات على يوتيوب</button></div>
      <p class="muted small">امسح عنوان أي لغة عشان متتحفظش. اللغات اللي على الفيديو ومش ظاهرة هنا بتفضل زي ما هي.</p>` : ''}
  </div>`;
}

// ---------- scheduled changes ----------
EDIT_TABS.schedule = {
  html: () => `
    <form class="panel" id="sched-form" autocomplete="off">
      <p class="muted small">غيّر عنوان أو وصف أو ثمبنيل في ميعاد، أو اخفي فيديو (Unlisted) في يوم معين. البرنامج بيفحص كل ساعة، فالتغيير بيحصل في خلال ساعة من الميعاد، وبس لو الداشبورد شغال (لو كان مقفول بيتنفذ أول ما يشتغل). كل تغيير ${WRITE_COST} وحدة.</p>
      <div class="row-inline wrap">
        <label class="grow">لينك الفيديو <input name="url" placeholder="https://youtu.be/..."></label>
        <label>التغيير <select name="kind">
          <option value="title">عنوان جديد</option><option value="description">وصف جديد</option>
          <option value="thumbnail">ثمبنيل جديد</option><option value="privacy">إخفاء / تغيير الظهور</option></select></label>
        <label>الميعاد <input name="when" type="datetime-local"></label>
      </div>
      <label data-kind="title">العنوان الجديد <input name="title" maxlength="100"></label>
      <label data-kind="description">الوصف الجديد <textarea name="description" rows="6"></textarea></label>
      <label data-kind="thumbnail">الصورة (PNG أو JPG، أقل من 2MB) <input name="thumb" type="file" accept="image/png,image/jpeg"></label>
      <label data-kind="privacy">يبقى <select name="privacy"><option value="unlisted">غير مدرج (Unlisted)</option><option value="private">خاص</option><option value="public">عام</option></select></label>
      <div><button class="btn primary" type="submit">جدول التغيير</button></div>
    </form>
    <div class="section-head"><h2>المجدول</h2></div>
    <div id="sched-list"></div>`,
  init() {
    const form = $('#sched-form');
    const sync = () => $$('[data-kind]', form).forEach((el) => { el.hidden = el.dataset.kind !== form.kind.value; });
    form.kind.addEventListener('change', sync);
    sync();
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!needEdit()) return;
      try {
        const kind = form.kind.value;
        const value = kind === 'thumbnail' ? await readThumb(form.thumb) : kind === 'privacy' ? form.privacy.value : form[kind].value;
        if (!value) return toast('اكتب التغيير الأول');
        if (!form.when.value) return toast('اختار الميعاد');
        await api('/api/schedule', { method: 'POST', body: { url: form.url.value, kind, value, when: form.when.value } });
        toast('اتجدول');
        loadSchedule();
      } catch (err) { toast(err.message); }
    });
    $('#sched-list').addEventListener('click', async (e) => {
      const btn = e.target.closest('[data-cancel]');
      if (!btn || !confirm('تلغي التغيير ده؟')) return;
      await api(`/api/schedule/${btn.dataset.cancel}`, { method: 'DELETE' });
      loadSchedule();
    });
    loadSchedule();
  },
};

const SCHED_STATUS = { pending: 'مستني', done: 'اتنفذ', failed: 'فشل', cancelled: 'اتلغى' };

async function loadSchedule() {
  const box = $('#sched-list');
  try {
    const rows = await api('/api/schedule');
    box.innerHTML = rows.length ? table(rows, [
      { h: 'الفيديو', cls: 'title-cell', cell: (r) => `<a href="${ytLink(r.video_id)}" target="_blank" rel="noopener">${esc(r.video_title)}</a>` },
      { h: 'التغيير', cell: (r) => `${esc(r.label)}<div class="muted small clamp" dir="auto">${r.kind === 'thumbnail' ? `<img class="mini-thumb" src="${thumbUrl(r.value)}" alt="">` : esc(r.value)}</div>` },
      { h: 'الميعاد', cell: (r) => `<span class="num">${esc(r.run_at_local)}</span>` },
      { h: 'الحالة', cell: (r) => `<span class="badge ${r.status === 'done' ? 'hot' : ''}">${SCHED_STATUS[r.status]}</span>${r.result && r.status === 'failed' ? `<div class="muted small">${esc(r.result)}</div>` : ''}` },
      { h: '', cell: (r) => (r.status === 'pending' ? `<button class="btn ghost small" data-cancel="${r.id}">إلغاء</button>` : '') },
    ]) : empty('مفيش تغييرات مجدولة.');
  } catch (err) { box.innerHTML = errorBox(err.message); }
}

// ---------- A/B rotation ----------
const LETTERS = ['A', 'B', 'C'];

EDIT_TABS.ab = {
  html: () => `
    <div class="panel note">
      <p><b>الأول جرّب «Test & Compare» في YouTube Studio</b> (من صفحة تعديل الفيديو). بيقسم المشاهدين في نفس الوقت على 3 ثمبنيلات أو عناوين وبيختار بوقت المشاهدة، وده أدق من أي حاجة هنا.</p>
      <p class="muted small">لو مش متاح لقناتك أو عاوز تختبر حاجة تانية: البرنامج هنا بيبدّل بين النسخ كل كام يوم وبيقارن أرقام YouTube Analytics لكل نسخة. لأن النسخ بتشتغل ورا بعض مش في نفس الوقت، الفيديو الجديد بيميل للنسخة الأولى، فخلّي كل نسخة تاخد دورين على الأقل. نسبة النقر (CTR) مش متاحة في الـ API، فالمقارنة بالمشاهدات ووقت المشاهدة في اليوم. التبديل بيحصل بعد نص الليل بتوقيت أمريكا (حوالي 10 الصبح بتوقيت مصر) عشان كل نسخة تاخد أيام كاملة في YouTube Analytics، والداشبورد لازم يكون شغال. كل تبديل ${WRITE_COST} وحدة لكل حاجة بتتغيّر.</p>
    </div>
    <form class="panel" id="ab-form" autocomplete="off">
      <label>لينك الفيديو <input name="url" placeholder="https://youtu.be/..."></label>
      <p class="muted small">النسخة A هي العنوان والثمبنيل الحاليين. ضيف نسخة أو اتنين (عنوان و/أو ثمبنيل).</p>
      ${[1, 2].map((i) => `<div class="row-inline wrap">
        <label class="grow">عنوان النسخة ${LETTERS[i]} <input name="title${i}" maxlength="100" placeholder="سيبه فاضي عشان العنوان يفضل زي ما هو"></label>
        <label class="grow">ثمبنيل النسخة ${LETTERS[i]} <input name="thumb${i}" type="file" accept="image/png,image/jpeg"></label></div>`).join('')}
      <div class="row-inline wrap">
        <label>كل نسخة تفضل <select name="days">${[1, 2, 3, 7].map((d) => `<option value="${d}">${plural(d, 'يوم', 'أيام')}</option>`).join('')}</select></label>
        <label>عدد الأدوار <select name="rounds">${[1, 2, 3, 4].map((r) => `<option ${r === 2 ? 'selected' : ''}>${r}</option>`).join('')}</select></label>
      </div>
      <div><button class="btn primary" type="submit">ابدأ الاختبار</button></div>
    </form>
    <div class="section-head"><h2>الاختبارات</h2></div>
    <div id="ab-list"></div>
    <div id="ab-results"></div>`,
  init() {
    const form = $('#ab-form');
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!needEdit()) return;
      try {
        const variants = [];
        for (const i of [1, 2]) {
          const title = form[`title${i}`].value.trim();
          const thumbnail = await readThumb(form[`thumb${i}`]);
          if (title || thumbnail) variants.push({ title: title || null, thumbnail });
        }
        if (!variants.length) return toast('ضيف نسخة واحدة على الأقل');
        if (!confirm('هيبدأ الاختبار والنسخ هتتبدّل لوحدها على يوتيوب. متأكد؟')) return;
        await busy($('button[type=submit]', form), () => api('/api/ab', { method: 'POST', body: { url: form.url.value, variants, days: +form.days.value, rounds: +form.rounds.value } }));
        toast('بدأ الاختبار');
        form.reset();
        loadAB();
      } catch (err) { toast(err.message); }
    });
    $('#ab-list').addEventListener('click', async (e) => {
      const res = e.target.closest('[data-ab-results]');
      const keep = e.target.closest('[data-ab-keep]');
      if (res) loadABResults(+res.dataset.abResults);
      if (keep) {
        const [id, idx] = keep.dataset.abKeep.split(':').map(Number);
        if (!needEdit() || !confirm(`توقّف الاختبار وتسيب النسخة ${LETTERS[idx]} على الفيديو؟`)) return;
        try {
          await api(`/api/ab/${id}/finish`, { method: 'POST', body: { keep: idx } });
          toast(`النسخة ${LETTERS[idx]} هي اللي على الفيديو دلوقتي`);
          loadAB();
        } catch (err) { toast(err.message); }
      }
    });
    loadAB();
  },
};

function variantCell(v, i, current) {
  return `<div class="variant ${i === current ? 'live' : ''}">
    <span class="badge ${i === current ? 'hot' : ''}">${LETTERS[i]}${i === current ? ' · شغالة' : ''}</span>
    ${v.thumbnail ? `<img src="${thumbUrl(v.thumbnail)}" alt="">` : ''}
    <span dir="auto">${esc(v.title)}</span></div>`;
}

async function loadAB() {
  const box = $('#ab-list');
  try {
    const tests = await api('/api/ab');
    box.innerHTML = tests.length ? tests.map((t) => `<div class="panel ab-test">
      <div class="panel-head"><h3><a href="${ytLink(t.video_id)}" target="_blank" rel="noopener">${esc(t.video_title)}</a></h3>
        <span class="muted small">${t.status === 'running' ? `التبديل الجاي ${new Date(t.next_switch * 1000).toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' })}` : `خلص · على الفيديو دلوقتي: ${LETTERS[t.winner ?? 0]}`}</span></div>
      <div class="variants">${t.variants.map((v, i) => variantCell(v, i, t.status === 'running' ? t.current : t.winner)).join('')}</div>
      <div class="row-inline wrap">
        <button class="btn small" type="button" data-ab-results="${t.id}">النتايج</button>
        ${t.variants.map((_, i) => `<button class="btn small ghost" type="button" data-ab-keep="${t.id}:${i}">${t.status === 'running' ? 'وقّف وسيب' : 'حط'} ${LETTERS[i]}</button>`).join('')}
      </div></div>`).join('') : empty('مفيش اختبارات لسه.');
  } catch (err) { box.innerHTML = errorBox(err.message); }
}

async function loadABResults(id) {
  const box = $('#ab-results');
  box.innerHTML = loading('بيجيب الأرقام');
  try {
    const r = await api(`/api/ab/${id}`);
    box.innerHTML = `<div class="panel"><div class="panel-head"><h2>النتايج</h2><span class="muted small">${r.days_counted} يوم محسوب · الأرقام بتتأخر ${r.lag_days} يوم</span></div>
      ${r.note ? `<p class="muted small">${esc(r.note)}</p>` : ''}
      ${table(r.versions, [
        { h: 'النسخة', cls: 'title-cell', cell: (v) => variantCell(v, v.index, r.leader) },
        { h: 'أيام', cell: (v) => `<span class="num">${v.days}</span>` },
        { h: 'مشاهدات/يوم', cell: (v) => num(v.views_per_day) },
        { h: 'دقايق مشاهدة/يوم', cell: (v) => num(v.minutes_per_day) },
        { h: 'متوسط المشاهدة', cell: (v) => (v.avg_view_duration == null ? '—' : clock(v.avg_view_duration)) },
        { h: 'نسبة المشاهدة', cell: (v) => (v.avg_view_pct == null ? '—' : `<span class="num">${v.avg_view_pct}%</span>`) },
        { h: 'مشتركين/يوم', cell: (v) => num(v.subs_per_day) },
      ])}
      <p class="muted small">${r.leader != null ? `النسخة ${LETTERS[r.leader]} جابت أكتر وقت مشاهدة في اليوم (اللي يوتيوب بيهتم بيه). ` : ''}اليوم بيتحسب لنسخة لو كانت شغالة 20 ساعة منه على الأقل. فرق أقل من 10% غالبًا صدفة.</p></div>`;
  } catch (err) { box.innerHTML = errorBox(err.message); }
}

// ---------- playlists ----------
let plItems = [];
let plOrder = [];

EDIT_TABS.playlists = {
  html: () => `
    <div class="row-inline wrap"><label class="grow">القايمة <select id="pl-select"><option value="">بيحمّل...</option></select></label></div>
    <div class="grid pl-grid">
      <form class="panel" id="pl-add-form" autocomplete="off">
        <h2>ضيف فيديوهات</h2>
        <label>لينك في كل سطر <textarea name="videos" rows="4"></textarea></label>
        <p class="muted small">الفيديوهات اللي موجودة بالفعل بتتساب. كل فيديو ${WRITE_COST} وحدة.</p>
        <div><button class="btn primary" type="submit">ضيف للقايمة</button></div>
        <div id="pl-add-result"></div>
      </form>
      <div class="panel">
        <h2>رتّب القايمة</h2>
        <div class="row-inline wrap">
          <select id="pl-sort"><option value="">ترتيب يدوي (بالأسهم)</option><option value="newest">الأحدث الأول</option><option value="oldest">الأقدم الأول</option><option value="views">الأكتر مشاهدة</option><option value="title">حسب الاسم</option></select>
          <button class="btn primary" type="button" id="pl-apply" disabled>طبّق الترتيب</button>
        </div>
        <p class="muted small" id="pl-moves">القايمة لازم تكون مترتبة «يدوي» في YouTube Studio. كل فيديو بيتنقل ${WRITE_COST} وحدة.</p>
        <div id="pl-items"></div>
      </div>
    </div>`,
  async init() {
    const select = $('#pl-select');
    try {
      const lists = await api('/api/playlists');
      select.innerHTML = lists.length ? lists.map((p) => `<option value="${esc(p.id)}">${esc(p.title)} (${p.count})</option>`).join('') : '<option value="">مفيش قوايم</option>';
      if (lists.length) loadPlaylist();
    } catch (err) { $('#pl-items').innerHTML = errorBox(err.message); select.innerHTML = ''; }
    select.addEventListener('change', loadPlaylist);
    $('#pl-sort').addEventListener('change', () => {
      const s = $('#pl-sort').value;
      const by = { newest: (a, b) => b.published.localeCompare(a.published), oldest: (a, b) => a.published.localeCompare(b.published),
        views: (a, b) => b.views - a.views, title: (a, b) => a.title.localeCompare(b.title, 'ar') }[s];
      if (by) plOrder = [...plItems].sort(by).map((r) => r.item_id);
      renderPlaylist();
    });
    $('#pl-items').addEventListener('click', (e) => {
      const btn = e.target.closest('[data-move]');
      if (!btn) return;
      const [i, d] = btn.dataset.move.split(':').map(Number);
      const j = i + d;
      if (j < 0 || j >= plOrder.length) return;
      [plOrder[i], plOrder[j]] = [plOrder[j], plOrder[i]];
      $('#pl-sort').value = '';
      renderPlaylist();
    });
    $('#pl-apply').addEventListener('click', (e) => {
      if (!needEdit()) return;
      const n = countMoves();
      if (!confirm(`هيتنقل ${n} فيديو في القايمة (${n * WRITE_COST} وحدة). متأكد؟`)) return;
      busy(e.target, async () => {
        try {
          const r = await api(`/api/playlists/${select.value}/reorder`, { method: 'POST', body: { order: plOrder } });
          toast(`اتنقل ${r.moves} فيديو`);
          loadPlaylist();
        } catch (err) { toast(err.message); }
      });
    });
    $('#pl-add-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!needEdit()) return;
      const videos = e.target.videos.value.split('\n').map((l) => l.trim()).filter(Boolean);
      if (!videos.length || !confirm(`تضيف لحد ${videos.length} فيديو للقايمة؟ (${videos.length * WRITE_COST} وحدة بالكتير)`)) return;
      await busy($('button[type=submit]', e.target), async () => {
        try {
          const r = await api(`/api/playlists/${select.value}/add`, { method: 'POST', body: { videos } });
          $('#pl-add-result').innerHTML = results(r);
          loadPlaylist();
        } catch (err) { $('#pl-add-result').innerHTML = errorBox(err.message); }
      });
    });
  },
};

async function loadPlaylist() {
  const box = $('#pl-items');
  box.innerHTML = loading();
  try {
    plItems = await api(`/api/playlists/${$('#pl-select').value}`);
    plOrder = plItems.map((r) => r.item_id);
    $('#pl-sort').value = '';
    renderPlaylist();
  } catch (err) { box.innerHTML = errorBox(err.message); }
}

function countMoves() {
  // Same one-at-a-time moves the server makes.
  const cur = plItems.map((r) => r.item_id);
  let n = 0;
  plOrder.forEach((id, i) => {
    if (cur[i] !== id) { cur.splice(cur.indexOf(id), 1); cur.splice(i, 0, id); n += 1; }
  });
  return n;
}

function renderPlaylist() {
  const byId = Object.fromEntries(plItems.map((r) => [r.item_id, r]));
  const n = countMoves();
  $('#pl-apply').disabled = !n;
  $('#pl-apply').textContent = n ? `طبّق (${n} نقلة · ${n * WRITE_COST} وحدة)` : 'طبّق الترتيب';
  $('#pl-items').innerHTML = plOrder.length ? `<ol class="pl-list">${plOrder.map((id, i) => {
    const r = byId[id];
    return `<li class="${r.position !== i ? 'moved' : ''}"><img src="${esc(r.thumbnail)}" alt="" loading="lazy">
      <span class="t">${esc(r.title)}</span><span class="muted small">${num(r.views)}</span>
      <span class="arrows"><button class="btn ghost small" type="button" data-move="${i}:-1" title="لفوق">↑</button><button class="btn ghost small" type="button" data-move="${i}:1" title="لتحت">↓</button></span></li>`;
  }).join('')}</ol>` : empty('القايمة فاضية.');
}

// ---------- replies ----------
let replyRows = [];
let cannedList = [];

EDIT_TABS.replies = {
  html: () => `
    <form class="panel" id="rp-form" autocomplete="off">
      <p class="muted small">الكومنتات اللي لسه مرديتش عليها. اكتب الرد، أو اختار رد جاهز، أو خلّي الـ AI يكتب مسودة، وبعدين اضغط «ابعت» على كل رد لوحده. مفيش حاجة بتتبعت لوحدها. كل رد ${WRITE_COST} وحدة.</p>
      <div class="row-inline wrap">
        <label class="grow">فيديو معين (اختياري) <input name="video" placeholder="سيبه فاضي لآخر كومنتات القناة كلها"></label>
        <label class="check-inline"><input type="checkbox" name="unanswered" checked> اللي مرديتش عليها بس</label>
        <button class="btn primary" type="submit">هات الكومنتات</button>
        <button class="btn" type="button" id="rp-drafts">مسودات بالـ AI</button>
      </div>
    </form>
    <div id="rp-list"></div>
    <div class="section-head"><h2>ردود جاهزة</h2></div>
    <form class="panel" id="canned-form" autocomplete="off">
      <div id="canned-list"></div>
      <div class="row-inline wrap">
        <input name="name" placeholder="اسم الرد (مثلًا: شكر)">
        <input name="text" class="grow" placeholder="نص الرد. {name} = اسم صاحب الكومنت">
        <button class="btn" type="submit">احفظ</button>
      </div>
    </form>`,
  init() {
    loadCanned();
    $('#rp-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const f = e.target;
      const box = $('#rp-list');
      box.innerHTML = loading();
      try {
        replyRows = await api(`/api/replies/threads?${new URLSearchParams({ video: f.video.value, unanswered: f.unanswered.checked })}`);
        renderReplies();
      } catch (err) { box.innerHTML = errorBox(err.message); }
    });
    $('#rp-drafts').addEventListener('click', (e) => busy(e.target, async () => {
      if (!replyRows.length) return toast('هات الكومنتات الأول');
      try {
        const d = await api('/api/replies/drafts', { method: 'POST', body: { comments: replyRows.map((r) => ({ comment_id: r.comment_id, text: r.text, author: r.author })) } });
        $$('.reply').forEach((el) => {
          const t = $('textarea', el);
          if (!t.value.trim() && d.replies[el.dataset.id]) t.value = d.replies[el.dataset.id];
        });
        toast(`اتكتبت ${Object.keys(d.replies).length} مسودة ($${d.usage.cost_usd}). راجعها قبل ما تبعت.`);
      } catch (err) { toast(err.message); }
    }));
    $('#rp-list').addEventListener('change', (e) => {
      if (!e.target.matches('.canned-pick')) return;
      const c = cannedList.find((x) => String(x.id) === e.target.value);
      const el = e.target.closest('.reply');
      if (c) $('textarea', el).value = c.text.replace('{name}', el.dataset.author.replace(/^@/, ''));
      e.target.value = '';
    });
    $('#rp-list').addEventListener('click', async (e) => {
      const btn = e.target.closest('[data-send]');
      if (!btn || !needEdit()) return;
      const el = btn.closest('.reply');
      const text = $('textarea', el).value.trim();
      if (!text) return toast('اكتب الرد الأول');
      await busy(btn, async () => {
        try {
          await api('/api/replies/post', { method: 'POST', body: { comment_id: el.dataset.id, text } });
          el.classList.add('sent');
          el.querySelector('.reply-actions').innerHTML = '<span class="badge hot">اتبعت</span>';
        } catch (err) { toast(err.message); }
      });
    });
    $('#canned-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      try {
        cannedList = await api('/api/replies/canned', { method: 'POST', body: { name: e.target.name.value, text: e.target.text.value } });
        e.target.reset();
        renderCanned();
      } catch (err) { toast(err.message); }
    });
    $('#canned-list').addEventListener('click', async (e) => {
      const btn = e.target.closest('[data-del-canned]');
      if (!btn) return;
      cannedList = await api(`/api/replies/canned/${btn.dataset.delCanned}`, { method: 'DELETE' });
      renderCanned();
    });
  },
};

async function loadCanned() {
  try { cannedList = await api('/api/replies/canned'); } catch { cannedList = []; }
  renderCanned();
}

function renderCanned() {
  $('#canned-list').innerHTML = cannedList.length ? `<div class="chips">${cannedList.map((c) => `
    <span class="chip" title="${esc(c.text)}">${esc(c.name)} <button class="btn ghost small" type="button" data-del-canned="${c.id}">✕</button></span>`).join('')}</div>`
    : '<p class="muted small">مفيش ردود جاهزة لسه.</p>';
  $$('.canned-pick').forEach((s) => { s.innerHTML = cannedOptions(); });
}

const cannedOptions = () => `<option value="">رد جاهز</option>${cannedList.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join('')}`;

function renderReplies() {
  $('#rp-list').innerHTML = replyRows.length ? `<div class="reply-list">${replyRows.map((r) => `
    <div class="panel reply" data-id="${esc(r.comment_id)}" data-author="${esc(r.author)}">
      <div class="muted small">${esc(r.author)} · ${num(r.likes)} لايك · <a href="${ytLink(r.video_id)}&lc=${esc(r.comment_id)}" target="_blank" rel="noopener">افتح</a></div>
      <div dir="auto">${esc(r.text)}</div>
      <textarea rows="2" dir="auto" placeholder="ردك"></textarea>
      <div class="row-inline wrap reply-actions">
        <select class="canned-pick">${cannedOptions()}</select>
        <button class="btn small primary" type="button" data-send>ابعت</button>
      </div>
    </div>`).join('')}</div>` : empty('مفيش كومنتات محتاجة رد.');
}

// ---------- history ----------
EDIT_TABS.history = {
  html: () => `<p class="muted small">كل تعديل عمله البرنامج على قناتك (من الداشبورد أو Claude Code أو المواعيد). «رجّع» بيحط القيمة القديمة تاني (${WRITE_COST} وحدة).</p><div id="hist-list"></div>`,
  init() {
    loadHistory();
    $('#hist-list').addEventListener('click', async (e) => {
      const btn = e.target.closest('[data-undo]');
      if (!btn || !needEdit() || !confirm('ترجّع التعديل ده؟')) return;
      await busy(btn, async () => {
        try { await api(`/api/edit/undo/${btn.dataset.undo}`, { method: 'POST' }); toast('اترجع'); loadHistory(); } catch (err) { toast(err.message); }
      });
    });
  },
};

function describeChange(r) {
  if (r.action === 'snippet') {
    return ['title', 'description', 'tags'].filter((k) => JSON.stringify(r.before[k]) !== JSON.stringify(r.after[k]))
      .map((k) => ({ title: 'العنوان', description: 'الوصف', tags: 'التاجز' }[k])).join('، ');
  }
  if (r.action === 'privacy') return `${esc(r.before)} ← ${esc(r.after)}`;
  if (r.action === 'localizations') return Object.keys(r.after || {}).join(', ');
  if (r.action === 'reply') return `<span dir="auto">${esc(String(r.after).slice(0, 80))}</span>`;
  if (r.action === 'playlist') return r.after?.moves ? `نقل ${r.after.moves} فيديو` : 'إضافة فيديو';
  return '';
}

async function loadHistory() {
  const box = $('#hist-list');
  try {
    const rows = await api('/api/edit/history');
    box.innerHTML = rows.length ? table(rows, [
      { h: 'إمتى', cell: (r) => `<span class="num">${new Date(r.created * 1000).toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' })}</span>` },
      { h: 'الفيديو', cls: 'title-cell', cell: (r) => (r.video_id ? `<a href="${ytLink(r.video_id)}" target="_blank" rel="noopener">${esc(r.video_title || r.video_id)}</a>` : '—') },
      { h: 'التعديل', cell: (r) => `${esc(r.label)}<div class="muted small">${describeChange(r)}</div>` },
      { h: 'من', cell: (r) => `<span class="muted small">${esc(r.source)}</span>` },
      { h: '', cell: (r) => (r.can_undo ? `<button class="btn ghost small" data-undo="${r.id}">رجّع</button>` : '') },
    ]) : empty('لسه مفيش تعديلات.');
  } catch (err) { box.innerHTML = errorBox(err.message); }
}
