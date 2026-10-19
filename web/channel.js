'use strict';
// "قناتي": public data from your channel link (recent videos, audit, milestones, earnings, backup),
// then YouTube Analytics once the channel is linked with OAuth.

const meRoot = $('#me-root');
let meDays = 28;
let meLoaded = false;

onEnter.me = () => loadMe();

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

function delta(cur, prev) {
  if (!prev) return '';
  const d = ((cur - prev) / prev) * 100;
  return `<span class="delta ${d >= 0 ? 'up' : 'down'} num">${d >= 0 ? '+' : ''}${d.toFixed(0)}%</span> عن الفترة اللي قبلها`;
}

function fill(id, path, render) {
  const box = $(id);
  if (!box) return;
  box.innerHTML = loading();
  api(path)
    .then((data) => { box.innerHTML = render(data); })
    .catch((err) => {
      box.innerHTML = errorBox(err.message) + (err.auth ? '<p><a class="btn primary" href="/auth/login">اربط القناة تاني</a></p>' : '');
    });
}

function connectPanel() {
  return status.has_client
    ? `<div class="panel">
        <p>اربط قناتك عشان تشوف أرقامها الحقيقية: الكلمات اللي الناس بحثت بيها ووصلتلك، مصادر المشاهدات، أداء كل فيديو، والجمهور.</p>
        <p class="muted small">الصلاحية قراءة بس. البرنامج مش بيقدر يعدّل أو ينشر حاجة على قناتك.</p>
        <div><a class="btn primary" href="/auth/login">اربط قناتك</a></div>
      </div>`
    : `<div class="panel">
        <p>عشان أرقام YouTube Analytics محتاج <b>OAuth Client ID</b> و <b>Client Secret</b>.</p>
        <div><a class="btn primary" href="#settings">روح للإعدادات</a></div>
      </div>`;
}

async function loadMe(force = false) {
  if (meLoaded && !force) return;
  await loadStatus();
  meLoaded = true;
  const hasChannel = !!status.my_channel.id;
  meRoot.innerHTML = `
    <header class="view-head">
      <h1>قناتي${status.my_channel.title ? `: ${esc(status.my_channel.title)}` : ''}</h1>
      <p class="muted">من غير ربط: آخر فيديوهاتك ومشاهداتها في الساعة، وفحص صحة القناة، والأهداف، والأرباح التقديرية. بعد الربط: أرقام YouTube Analytics الحقيقية.</p>
    </header>
    ${hasChannel ? `
      <div class="section-head"><h2>آخر فيديوهاتك دلوقتي</h2><button class="btn small" id="me-recent-refresh">حدّث</button></div>
      <p class="muted small">المشاهدات في الساعة بتظهر بعد تحديثين بينهم نص ساعة على الأقل. البرنامج بيحدّث لوحده كل ساعة وهو مفتوح.</p>
      <div id="me-recent"></div>
      <div class="grid two">
        <div class="panel" id="me-milestones"></div>
        <div class="panel" id="me-earnings"></div>
      </div>
      <div class="section-head"><h2>فحص صحة القناة</h2>
        <form class="row-inline" id="audit-form"><input id="audit-channel" placeholder="أو افحص قناة تانية: @handle"><button class="btn small" type="submit">افحص</button></form>
      </div>
      <div id="me-audit"></div>
      <div class="section-head"><h2>نسخة احتياطية</h2></div>
      <div class="panel" id="me-backup">
        <p class="muted small">بيحفظ عنوان ووصف وتاجز وأرقام كل فيديوهاتك في ملف JSON و CSV (بيفتح في Excel). حوالي وحدتين quota لكل 50 فيديو.</p>
        <div><button class="btn" id="backup-run">اعمل نسخة دلوقتي</button></div>
        <div id="backup-list"></div>
      </div>`
    : `<div class="panel"><p>حط لينك قناتك في الإعدادات (أو اربطها تحت) عشان تظهر هنا: آخر فيديوهاتك، وفحص صحة القناة، والأهداف، والأرباح التقديرية.</p>
        <div><a class="btn primary" href="#settings">حط لينك القناة</a></div></div>`}
    <div class="section-head">
      <h2>YouTube Analytics</h2>
      ${status.connected ? `<div class="filters">
        <select id="me-days">${[7, 28, 90, 365].map((d) => `<option value="${d}" ${d === meDays ? 'selected' : ''}>آخر ${d} يوم</option>`).join('')}</select>
        <button class="btn ghost small" id="me-logout">افصل القناة</button></div>` : ''}
    </div>
    <div id="me-analytics"></div>`;

  if (hasChannel) {
    loadRecent();
    fill('#me-milestones', '/api/milestones', renderMilestones);
    loadEarnings();
    fill('#me-audit', '/api/audit', renderAudit);
    loadBackups();
  }
  if (status.has_client && status.connected) loadAnalytics();
  else $('#me-analytics').innerHTML = connectPanel();
}

// ---------- recent videos ----------
function loadRecent() {
  fill('#me-recent', '/api/me/recent', (d) => table(d.videos, [
    'video', 'views', 'vph',
    { h: 'آخر 48 ساعة', cell: (v) => (v.last_48h == null ? '<span class="muted small">—</span>' : num(v.last_48h)) },
    'vpd', 'age',
  ]));
}

// ---------- milestones ----------
function renderMilestones(m) {
  const goal = (label, g) => (g ? `
    <div class="milestone">
      <div class="panel-head"><span>${label}: <b class="num">${fmt(g.current)}</b> من <b class="num">${fmt(g.next)}</b></span><span class="muted small num">${g.progress}%</span></div>
      <div class="meter"><span style="width:${g.progress}%"></span></div>
      <div class="muted small">${g.eta ? `بالمعدل الحالي هتوصل حوالي <span class="num">${g.eta}</span> (بعد ${plural(g.days, 'يوم', 'أيام')})` : 'المعدل لسه مش معروف. بيظهر بعد كام يوم من التحديث أو بعد ربط القناة.'}</div>
    </div>` : '');
  const ypp = m.partner_program;
  return `
    <h2>الأهداف</h2>
    ${goal('المشتركين', m.subs)}
    ${goal('المشاهدات', m.views)}
    <div class="milestone">
      <div class="panel-head"><span>برنامج الشركاء</span></div>
      <div class="muted small">مشتركين: <span class="num">${fmt(ypp.subs)} / 1K</span> · ساعات مشاهدة آخر 12 شهر: <span class="num">${ypp.watch_hours == null ? 'اربط القناة' : `${fmt(ypp.watch_hours)} / 4K`}</span></div>
    </div>
    ${m.achieved.length ? `<div class="chips">${m.achieved.map((a) => `<span class="chip"><span class="nuqta small"></span><span class="num">${fmt(a)}</span> مشترك</span>`).join('')}</div>` : ''}
    ${m.source ? `<p class="muted small">المعدل ${esc(m.source)}.</p>` : ''}`;
}

// ---------- earnings ----------
function loadEarnings(rpm) {
  fill('#me-earnings', `/api/earnings${rpm ? `?rpm=${rpm}` : ''}`, (e) => `
    <div class="panel-head"><h2>الأرباح التقديرية</h2>
      <form class="row-inline" id="rpm-form"><label class="check-inline">RPM $<input id="rpm-input" class="tiny" type="number" step="0.1" min="0" value="${e.rpm}"></label><button class="btn small" type="submit">احسب</button></form>
    </div>
    <div class="grid kpis">
      ${statCard('في الشهر', `<span class="num">$${fmt(e.monthly.mid)}</span>`, `بين $${fmt(e.monthly.low)} و $${fmt(e.monthly.high)}`)}
      ${statCard('في السنة', `<span class="num">$${fmt(e.yearly)}</span>`)}
    </div>
    <p>قيمة القناة لو اتباعت: <b class="num">$${fmt(e.valuation.low)} – $${fmt(e.valuation.high)}</b> <span class="muted small">(من 24 لـ 36 ضعف الدخل الشهري)</span></p>
    <p class="muted small">مبني على <span class="num">${fmt(e.monthly_views)}</span> مشاهدة في الشهر (${esc(e.source)}). ${esc(e.note)}</p>`);
}

meRoot.addEventListener('submit', (e) => {
  if (e.target.id === 'rpm-form') {
    e.preventDefault();
    loadEarnings($('#rpm-input').value);
  } else if (e.target.id === 'audit-form') {
    e.preventDefault();
    const ch = $('#audit-channel').value.trim();
    fill('#me-audit', `/api/audit${ch ? `?channel=${encodeURIComponent(ch)}` : ''}`, renderAudit);
  }
});

// ---------- audit ----------
function renderAudit(a) {
  if (a.empty) return empty('القناة دي مفيهاش فيديوهات.');
  const t = tone(a.score);
  const st = a.stats;
  return `
    <div class="grid two">
      <div class="panel">
        <div class="panel-head"><h2>${esc(a.channel.title)}</h2><span class="muted small">آخر ${st.videos_checked} فيديو</span></div>
        <div class="score-big ${t} num">${a.score}</div>
        <div class="meter ${t === 'bad' ? 'rust' : ''}"><span style="width:${a.score}%"></span></div>
        <div class="checks">${a.checks.map((c) => `
          <div class="check ${c.status}"><span class="mark"></span><span>${esc(c.label)}: <span class="muted">${esc(c.value)}</span></span>${c.tip ? `<span class="tip">${esc(c.tip)}</span>` : ''}</div>`).join('')}</div>
      </div>
      <div class="view">
        <div class="grid kpis">
          ${statCard('المعتاد للفيديو الطويل', num(st.long_median))}
          ${statCard('المعتاد للشورت', num(st.shorts_median))}
          ${statCard('نسبة الشورتس', `<span class="num">${st.shorts_share}%</span>`)}
        </div>
        ${a.best.length ? `<h3>أحسن فيديوهات مقارنة بالمعتاد</h3>${table(a.best, ['video', 'outlier', 'views'])}` : ''}
        ${a.worst.length ? `<h3>أضعف فيديوهات</h3>${table(a.worst, ['video', 'outlier', 'views'])}` : ''}
      </div>
    </div>`;
}

// ---------- backup ----------
async function loadBackups() {
  try {
    const files = await api('/api/backups');
    $('#backup-list').innerHTML = files.length
      ? `<h3>النسخ المحفوظة</h3><div class="chips">${files.slice(0, 10).map((f) => `<a class="chip" href="/api/backups/${encodeURIComponent(f)}" download>${esc(f)}</a>`).join('')}</div>`
      : '';
  } catch { /* the list is optional */ }
}

meRoot.addEventListener('click', async (e) => {
  const id = e.target.id;
  if (id === 'me-recent-refresh') {
    loadRecent();
  } else if (id === 'backup-run') {
    await busy(e.target, async () => {
      try {
        const r = await api('/api/backup', { method: 'POST' });
        toast(`اتحفظ ${r.count} فيديو`);
        loadBackups();
      } catch (err) { toast(err.message); }
    });
  } else if (id === 'me-logout') {
    $('#me-logout').hidden = true;
    meRoot.querySelector('#me-analytics').innerHTML = `<div class="panel"><p>تفصل القناة من البرنامج؟</p>
      <div class="row-inline"><button class="btn primary" id="me-logout-yes">افصلها</button><button class="btn" id="me-logout-no">لأ</button></div></div>`;
  } else if (id === 'me-logout-yes') {
    await api('/auth/logout', { method: 'POST' });
    loadMe(true);
  } else if (id === 'me-logout-no') {
    loadMe(true);
  }
  const term = e.target.closest('[data-analyze-term]');
  if (term) analyzeKeyword(term.dataset.analyzeTerm);
});

meRoot.addEventListener('change', (e) => {
  if (e.target.id === 'me-days') {
    meDays = +e.target.value;
    loadAnalytics();
  }
});

// ---------- YouTube Analytics ----------
function loadAnalytics() {
  $('#me-analytics').innerHTML = `
    <div id="me-overview"></div>
    <div class="grid two">
      <div class="panel"><div class="panel-head"><h2>الناس بحثت عن إيه ووصلتلك</h2></div>
        <p class="muted small">دي الكلمات الحقيقية من بحث يوتيوب. اضغط «حلل» عشان تشوف فرصتها.</p>
        <div id="me-terms"></div></div>
      <div class="panel"><h2>المشاهدات جاية منين</h2><div id="me-traffic"></div></div>
    </div>
    <div class="section-head"><h2>أداء الفيديوهات في الفترة دي</h2></div>
    <p class="muted small">انسخ لينك أي فيديو في «تحليل فيديو» واضغط «الناس بتمشي فين؟» عشان تشوف الاحتفاظ.</p>
    <div id="me-videos"></div>
    <div class="section-head"><h2>الجمهور</h2></div>
    <div id="me-audience"></div>`;
  const q = `?days=${meDays}`;

  fill('#me-overview', `/api/me/overview${q}`, (o) => {
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

  fill('#me-terms', `/api/me/search-terms${q}`, (rows) => (rows.length ? table(rows, [
    { h: 'الكلمة', cell: (r) => esc(r.insightTrafficSourceDetail) },
    { h: 'المشاهدات', cell: (r) => num(r.views) },
    { h: '', cell: (r) => `<button class="btn small" data-analyze-term="${esc(r.insightTrafficSourceDetail)}">حلل</button>` },
  ]) : empty('مفيش مشاهدات من البحث في الفترة دي.')));

  fill('#me-traffic', `/api/me/traffic${q}`, (rows) => {
    const total = rows.reduce((sum, r) => sum + r.views, 0) || 1;
    return rows.length ? bars(rows.map((r) => ({ label: r.label, value: r.views, text: `${((r.views / total) * 100).toFixed(0)}%` })), { best: false }) : empty('مفيش داتا.');
  });

  fill('#me-videos', `/api/me/videos${q}`, (rows) => (rows.length ? table(rows, [
    'video', 'views',
    { h: 'ساعات المشاهدة', cell: (r) => num(r.estimatedMinutesWatched / 60) },
    { h: 'متوسط المدة', cell: (r) => clock(r.averageViewDuration) },
    { h: 'نسبة المشاهدة', cell: (r) => `<span class="num">${r.averageViewPercentage.toFixed(0)}%</span>` },
    { h: 'مشتركين جداد', cell: (r) => num(r.subscribersGained) },
  ]) : empty('مفيش مشاهدات في الفترة دي.')));

  fill('#me-audience', `/api/me/audience${q}`, (a) => {
    const byAge = {}, byGender = {};
    for (const r of a.demographics) {
      const age = r.ageGroup.replace('age', '').replace('-', '–');
      byAge[age] = (byAge[age] || 0) + r.viewerPercentage;
      byGender[r.gender] = (byGender[r.gender] || 0) + r.viewerPercentage;
    }
    const genderLabel = { male: 'رجالة', female: 'ستات', user_specified: 'محدد من المستخدم' };
    return `<div class="grid two">
      <div class="panel"><h3>أكتر الدول</h3>${a.countries.length ? bars(a.countries.map((r) => {
        let name = r.country;
        try { name = regionNames.of(r.country); } catch { /* unknown code */ }
        return { label: name, value: r.views, text: fmt(r.views) };
      }), { best: false }) : empty('مفيش داتا.')}</div>
      <div class="panel"><h3>السن والنوع</h3>${Object.keys(byAge).length
        ? bars(Object.entries(byAge).map(([k, v]) => ({ label: k, value: v, text: `${v.toFixed(0)}%` })), { best: false })
          + bars(Object.entries(byGender).map(([k, v]) => ({ label: genderLabel[k] || k, value: v, text: `${v.toFixed(0)}%` })), { best: false })
        : empty('يوتيوب مش بيعرض السن والنوع غير لما يبقى فيه مشاهدات كفاية.')}</div>
    </div>`;
  });
}
