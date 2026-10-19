# YouTube Studio

أداة يوتيوب مجانية ومفتوحة المصدر، بديلة لـ vidIQ و TubeBuddy. بتشتغل على جهازك، من غير اشتراك ومن غير سيرفر.

A free, open-source alternative to vidIQ and TubeBuddy that runs on your own computer. [English below](#english).

---

## المميزات

| الصفحة | بتعمل إيه | التكلفة من الـ quota |
| --- | --- | --- |
| الكلمات المفتاحية | اقتراحات البحث وإنت بتكتب، وتقييم للطلب والمنافسة، والتاجز الأكتر استخدامًا، وأول 25 نتيجة | الاقتراحات مجانية، والتحليل حوالي 102 |
| تحليل فيديو | تاجز أي فيديو، وأداءه مقارنة بقناته، وتقييم SEO | حوالي 4 |
| SEO | فحص العنوان والوصف والتاجز وإنت بتكتب | مجاني |
| المنافسين | متابعة قنوات، والفيديوهات اللي فرقعت (Outliers)، وأحسن وقت للنشر | حوالي 3 لكل قناة كل 12 ساعة |
| قناتي | أرقامك الحقيقية: الكلمات اللي الناس بحثت بيها ووصلتلك، ومصادر المشاهدات، وأداء الفيديوهات، والجمهور | quota منفصلة ومش بتخلص عمليًا |

الـ quota المجانية من جوجل 10,000 وحدة في اليوم، يعني حوالي 90 تحليل كلمة في اليوم. بتتجدد حوالي الساعة 10 الصبح بتوقيت مصر.

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
- **OAuth Client ID و Secret** (نوع Desktop app): عشان صفحة «قناتي» بس. الصلاحية قراءة فقط.

المفاتيح بتتحفظ في ملف `.env` على جهازك، ومش بتتبعت لأي حد غير جوجل.

## الاستخدام من Claude Code

نفس المميزات متاحة كأدوات (MCP) جوه Claude Code، فتقدر تقوله مثلًا «حلل كلمة شرح Claude وقارنها بشرح ChatGPT» أو «إيه الكلمات اللي الناس بحثت بيها ووصلت لقناتي الشهر ده». من فولدر مشروعك:

```bash
claude mcp add youtube-studio -- "<مكان المشروع>/.venv/Scripts/python.exe" "<مكان المشروع>/mcp_server.py"
```

لازم تشغّل `run.bat` مرة الأول عشان المكتبات تتسطّب، وتربط قناتك من الداشبورد لو عاوز أدوات «قناتي». الداشبورد والـ MCP بيستخدموا نفس المفاتيح ونفس البيانات.

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

- **Keyword research:** live YouTube autocomplete, a 0–100 score for demand vs. competition, most-used tags, and the top 25 results with views/day and views-to-subscribers ratio.
- **Video analyzer:** any video's tags, its performance against its channel's usual, engagement, and an SEO checklist.
- **SEO checker:** scores your title, description and tags as you type.
- **Competitors:** track channels, find their outlier videos, and see which weekday and hour perform best.
- **My channel** (OAuth, read-only): the real search terms that brought viewers, traffic sources, per-video performance, countries, age and gender.

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

**How scores work.** vidIQ's search volume comes from its own user data, which no public API provides. Here, *demand* comes from how fast the top results gain views and how early autocomplete suggests the phrase; *competition* comes from the size of the ranking channels and how many of them use the phrase in their title. Treat the numbers as a way to compare keywords, not as real search counts.

The free YouTube Data API quota is 10,000 units/day: about 90 keyword analyses. Change the default region (EG) and language (ar) in Settings.

**Stack:** Python, FastAPI, SQLite, plain HTML/CSS/JS. No build step.

## License

[MIT](LICENSE)
