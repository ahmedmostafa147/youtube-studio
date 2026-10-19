# YouTube Studio

أداة يوتيوب مجانية ومفتوحة المصدر، بديلة لـ vidIQ و TubeBuddy. بتشتغل على جهازك، من غير اشتراك ومن غير سيرفر.

A free, open-source alternative to vidIQ and TubeBuddy that runs on your own computer. [English below](#english).

---

## المميزات

| الصفحة | بتعمل إيه | التكلفة من الـ quota |
| --- | --- | --- |
| الأفكار | تنبيهات لما منافس ينزّل فيديو أو فيديو يفرقع أو حاجة في مجالك تدخل الترند، وأفكار يومية بالـ AI، ومخطط للفيديوهات الجاية، والترند في بلدك | حوالي 3 لكل منافس في الساعة وهو مفتوح |
| الكلمات المفتاحية | اقتراحات البحث وإنت بتكتب، وتقييم للطلب والمنافسة، والتاجز الأكتر استخدامًا، وأول 25 نتيجة | الاقتراحات مجانية، والتحليل حوالي 102 |
| الكتابة بالـ AI | عناوين، ووصف وتاجز، وسكريبت، و Chapters من الترانسكريبت، بصوت قناتك | مجاني من الـ quota (بيتحاسب على Claude API) |
| الثمبنيل | معاينة الثمبنيل بأحجامه الحقيقية وجنب فيديوهات المنافسين، وفحص التباين، وتقييم بالـ AI | مجاني |
| SEO | فحص العنوان والوصف والتاجز وإنت بتكتب، وترتيب التاجز وقوايم محفوظة، وفحص الكلمات اللي بتقلل الإعلانات | مجاني |
| تحليل فيديو | تاجز أي فيديو، وأداءه مقارنة بقناته، وتقييم SEO، وتحليل الكومنتات، والاحتفاظ (لفيديوهاتك) | حوالي 4، والكومنتات حوالي 3 |
| المنافسين | مقارنة قناتك بالمنافسين، والفيديوهات اللي فرقعت مع المشاهدات في الساعة، وأحسن وقت للنشر | حوالي 3 لكل قناة |
| قناتي | آخر فيديوهاتك ومشاهداتها في الساعة، وفحص صحة القناة، والأهداف، والأرباح التقديرية، ونسخة احتياطية. وبعد الربط: الكلمات اللي الناس بحثت بيها ووصلتلك، ومصادر المشاهدات، والجمهور | قليلة، و Analytics ليها quota منفصلة |
| تعديل القناة | تعديل جماعي (دوّر واستبدل، أو ضيف سطر في أول/آخر الوصف أو العنوان)، وقوالب للعنوان والوصف والتاجز، وترجمة العنوان والوصف للغات تانية، وتغييرات في ميعاد (عنوان، وصف، ثمبنيل، إخفاء الفيديو)، واختبار A/B بالتبديل، وإضافة وترتيب قوايم التشغيل، والرد على الكومنتات بردود جاهزة أو مسودات بالـ AI، وسجل لكل تعديل مع زرار «رجّع» | المعاينة ببلاش تقريبًا، وكل تعديل 50 |
| ترتيبك في البحث | ترتيب الفيديو في البحث لكل تاج، ومتابعة ترتيبك يوميًا لكلمات بتختارها، وتنبيه لما حد يذكر اسم قناتك | 100 لكل كلمة (والمتابعة 100 لكل كلمة في اليوم) |

الكتابة بالـ AI من الداشبورد محتاجة Claude API key. من Claude Code مش محتاجاه: Claude بيكتب بنفسه وبيستخدم أدوات البرنامج.

الـ quota المجانية من جوجل 10,000 وحدة في اليوم، يعني حوالي 90 تحليل كلمة في اليوم. بتتجدد حوالي الساعة 10 الصبح بتوقيت مصر.

### التعديل على القناة (مقفول افتراضيًا)

البرنامج بيقرأ بس لحد ما تفعّل «اسمح للبرنامج يعدّل على قناتك» من الإعدادات وتربط القناة تاني. ساعتها جوجل بتطلب صلاحية `youtube.force-ssl` (تعديل العناوين والوصف والثمبنيل والظهور وقوايم التشغيل والرد على الكومنتات). وبعد كده:

- كل تعديل بيبدأ بمعاينة، ومفيش حاجة بتتغيّر غير لما تختار الفيديوهات بنفسك وتدوس تطبيق. الردود على الكومنتات مش بتتبعت غير لما تدوس «ابعت» على كل رد.
- الفيديو بيتقري تاني قبل التعديل مباشرة، والقيمة القديمة بتتحفظ في «السجل» عشان ترجّعها بزرار (والثمبنيل القديم بيتحفظ نسخة منه).
- التغييرات المجدولة واختبارات A/B بتتنفذ من الفحص اللي بيحصل كل ساعة، يعني في خلال ساعة من الميعاد وبس لو الداشبورد شغال.
- اختبار A/B هنا بيبدّل النسخ ورا بعض كل كام يوم ويقارن أرقام Analytics. لو قناتك عندها «Test & Compare» في YouTube Studio استخدمه الأول، لأنه بيقسم المشاهدين في نفس الوقت وأدق.
- لو قفلت التعديل تاني من الإعدادات، كل التعديلات بتتوقف فورًا.

## التشغيل على ويندوز

1. سطّب [Python](https://www.python.org/downloads/) (3.11 أو أحدث)، وعلّم على «Add Python to PATH» وإنت بتسطّب.
2. نزّل المشروع: زرار **Code** الأخضر ← **Download ZIP**، وفك الضغط.
3. دبل كليك على `run.bat`. أول مرة بيسطّب المكتبات لوحده، وبعدين بيفتح `http://127.0.0.1:8765` في المتصفح.
4. روح لصفحة **الإعدادات** جوه البرنامج وحط المفاتيح. الخطوات مكتوبة هناك وبتاخد حوالي 10 دقايق مرة واحدة.

على ماك أو لينكس:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python run.py
```

## المفاتيح (مجانية)

كل واحد بيستخدم مفاتيحه هو من [Google Cloud](https://console.cloud.google.com/):

- **YouTube API key:** كفاية للكلمات والمنافسين وتحليل الفيديو.
- **OAuth Client ID و Secret** (نوع Desktop app): عشان صفحة «قناتي». الصلاحية قراءة فقط، إلا لو فعّلت التعديل من الإعدادات.

المفاتيح بتتحفظ في ملف `.env` على جهازك، ومش بتتبعت لأي حد غير جوجل.

## الاستخدام من Claude Code

نفس المميزات متاحة كأدوات (MCP) جوه Claude Code، فتقدر تقوله مثلًا «حلل كلمة شرح Claude وقارنها بشرح ChatGPT» أو «إيه الكلمات اللي الناس بحثت بيها ووصلت لقناتي الشهر ده». من فولدر مشروعك:

```bash
claude mcp add youtube-studio -- "<مكان المشروع>/.venv/Scripts/python.exe" "<مكان المشروع>/mcp_server.py"
```

لازم تشغّل `run.bat` مرة الأول عشان المكتبات تتسطّب، وتربط قناتك من الداشبورد لو عاوز أدوات «قناتي». الداشبورد والـ MCP بيستخدموا نفس المفاتيح ونفس البيانات.

أدوات التعديل من Claude Code (زي `edit_video` و `bulk_edit_apply` و `save_localizations` و `reply_to_comment`) بتعمل معاينة بس، ومش بتغيّر حاجة غير لو اتنادت بـ `confirm=true` بعد ما توافق إنت على المعاينة.

## الاختبارات

اختبارات المرحلة التانية بتشتغل على داتا وهمية (من غير نت ومن غير ما تلمس بياناتك):

```bash
.venv/Scripts/python.exe tests/run_phase2.py
```

## إزاي الأرقام بتتحسب

- **الطلب:** سرعة مشاهدات أول 10 نتايج (مشاهدة في اليوم)، وأد إيه يوتيوب بيقترح الجملة بدري وإنت بتكتبها.
- **المنافسة:** حجم القنوات اللي في أول 10 نتايج، وكام واحد فيهم حاطط الكلمة في العنوان.
- **Outlier:** مشاهدات الفيديو ÷ المعتاد لقناته (الوسيط لآخر فيديوهاتها من نفس النوع).

vidIQ عنده رقم «حجم البحث» من داتا ملايين اليوزرز، وده مش موجود في أي API. أرقام الأداة دي تقدير بيقارن الكلمات ببعض، مش رقم بحث حقيقي.

الدولة واللغة الافتراضيين مصر والعربي، وتقدر تغيّرهم من الإعدادات.

---

## English

A local dashboard for YouTube creators. The interface is in Arabic.

**Features**

- **Ideas & alerts:** background checks every hour (while the dashboard runs) for new competitor uploads, competitor videos taking off, and niche videos entering trending; AI daily ideas; a video planner board; trending videos for your region.
- **AI writing** (Claude API key, or free from Claude Code): titles ranked by an SEO check, description + tags, script outline, chapters from an `.srt` transcript.
- **Thumbnails:** preview at real sizes and next to competitors' videos, contrast/brightness checks, AI review.
- **Channel insights:** recent videos with views per hour, channel audit, milestones with ETA, earnings estimate, scorecard vs competitors, retention curve (OAuth), comment insights, ad-safety word check, full metadata backup (JSON + CSV).
- **Keyword research:** live YouTube autocomplete, a 0–100 score for demand vs. competition, most-used tags, and the top 25 results with views/day and views-to-subscribers ratio.
- **Video analyzer:** any video's tags, its performance against its channel's usual, engagement, and an SEO checklist.
- **SEO checker:** scores your title, description and tags as you type.
- **Competitors:** track channels, find their outlier videos, and see which weekday and hour perform best.
- **My channel** (OAuth, read-only): the real search terms that brought viewers, traffic sources, per-video performance, countries, age and gender.
- **Edit my channel** (opt-in, see below): bulk find/replace/append in titles or descriptions with a dry-run preview and per-video selection; upload profiles (title/description templates with `{title}`, `{description}`, `{date}`, plus tags and category); AI translation of title and description saved as video localizations; scheduled title/description/thumbnail changes and "sunset" (unlist or make private on a date); title/thumbnail A/B rotation with an analytics comparison; playlist add and reorder; canned comment replies and AI reply drafts, posted only when you press send; a log of every change with one-click undo.
- **Search ranks:** a video's rank for each of its tags, daily rank tracking for chosen keywords, and daily brand-mention alerts. These use `search.list` at 100 quota units per keyword, so the number of tracked keywords is capped in Settings (default 5 = 500 units/day) and every button shows its cost.

**Editing is off by default.** The OAuth sign-in is read-only until you tick "allow editing" in Settings and link the channel again, which adds the `youtube.force-ssl` scope. Every change costs 50 quota units, re-reads the video right before writing, and is logged with the old value. Scheduled changes and A/B switches run from the hourly background check, so they happen within an hour of their time and only while the dashboard is running; A/B switches land just after midnight Pacific time so each version owns whole YouTube Analytics days. YouTube Studio's built-in Test & Compare splits viewers at the same time and is more accurate when your channel has it. Turning editing off stops all writes immediately.

**Run**

Install Python 3.11+, then double-click `run.bat` on Windows, or on macOS/Linux:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python run.py
```

Open the **Settings** page (الإعدادات) and add your own free Google Cloud keys: a YouTube Data API key, plus a Desktop-app OAuth client for the "my channel" page. Keys are stored in `.env` on your machine only.

**Claude Code (MCP).** The same features are available as MCP tools (`analyze_keyword`, `keyword_ideas`, `analyze_video`, `seo_check`, `competitor_outliers`, `my_search_terms`, …). After running `run.bat` once:

```bash
claude mcp add youtube-studio -- "<repo>/.venv/Scripts/python.exe" "<repo>/mcp_server.py"
```

The dashboard and the MCP server share the same keys and data. Link your channel from the dashboard for the `my_*` tools.

MCP tools that change the channel (`edit_video`, `bulk_edit_apply`, `apply_upload_profile`, `save_localizations`, `schedule_change`, `start_ab_test`, `finish_ab_test`, `add_to_playlist`, `reorder_playlist`, `reply_to_comment`, `undo_edit`) return a preview and change nothing unless called with `confirm=true`. Read and preview tools (`bulk_edit_preview`, `video_details`, `tag_rankings`, `tracked_keywords`, `ab_test_results`, `unanswered_comments`, …) need no confirmation.

**Tests.** `tests/run_phase2.py` runs the Phase 2 features against fake YouTube, Analytics and Claude responses (no network, temp data folder).

**How scores work.** vidIQ's search volume comes from its own user data, which no public API provides. Here, *demand* comes from how fast the top results gain views and how early autocomplete suggests the phrase; *competition* comes from the size of the ranking channels and how many of them use the phrase in their title. Treat the numbers as a way to compare keywords, not as real search counts.

The free YouTube Data API quota is 10,000 units/day: about 90 keyword analyses. Change the default region (EG) and language (ar) in Settings.

**Stack:** Python, FastAPI, SQLite, plain HTML/CSS/JS. No build step.

## License

[MIT](LICENSE)
