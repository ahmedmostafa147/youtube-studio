"""Checklist score for a video's title, description and tags."""

import re

from . import util

TIMESTAMP = re.compile(r"^\s*\(?(\d{1,2}:)?\d{1,2}:\d{2}\)?", re.M)
HASHTAG = re.compile(r"#[\w؀-ۿ]+")


def tags_length(tags):
    # YouTube's 500-character limit counts commas between tags and quotes around multi-word tags.
    return sum(len(t) + (2 if " " in t else 0) for t in tags) + max(len(tags) - 1, 0)


def score(title, description, tags, keyword):
    title, description, keyword = title.strip(), description.strip(), keyword.strip()
    tags = [t.strip() for t in tags if t.strip()]
    checks = []

    def check(group, label, status, points, tip=""):
        earned = points if status == "pass" else points / 2 if status == "warn" else 0
        checks.append({"group": group, "label": label, "status": status, "points": points, "earned": earned, "tip": tip})

    # ----- title -----
    if keyword:
        if util.has_phrase(title, keyword):
            check("العنوان", "الكلمة المستهدفة في العنوان", "pass", 15)
            pos = util.normalize(title).find(util.normalize(keyword))
            early = pos <= len(util.normalize(title)) / 3
            check("العنوان", "الكلمة في أول العنوان", "pass" if early else "warn", 5,
                  "" if early else "قدّم الكلمة لأول العنوان. يوتيوب والمشاهد بيدّوا وزن أكبر لأول كلمتين.")
        elif util.has_all_words(title, keyword):
            check("العنوان", "الكلمة المستهدفة في العنوان", "warn", 15, "كلمات الجملة موجودة بس متفرقة. حطها جملة واحدة زي ما الناس بتبحث.")
            check("العنوان", "الكلمة في أول العنوان", "warn", 5)
        else:
            check("العنوان", "الكلمة المستهدفة في العنوان", "fail", 15, "حط الكلمة المستهدفة في العنوان بالظبط.")
            check("العنوان", "الكلمة في أول العنوان", "fail", 5)

    n = len(title)
    if 20 <= n <= 70:
        check("العنوان", f"طول العنوان ({n} حرف)", "pass", 10)
    elif n < 20:
        check("العنوان", f"طول العنوان ({n} حرف)", "warn", 10, "العنوان قصير. استغل المساحة لحد 60-70 حرف.")
    elif n <= 100:
        check("العنوان", f"طول العنوان ({n} حرف)", "warn", 10, "اللي بعد حوالي 70 حرف بيتقص في نتايج البحث. خلّي المهم في الأول.")
    else:
        check("العنوان", f"طول العنوان ({n} حرف)", "fail", 10, "يوتيوب مش بيقبل أكتر من 100 حرف.")

    # ----- description -----
    if keyword:
        early = util.has_phrase(description[:150], keyword)
        check("الوصف", "الكلمة في أول سطرين", "pass" if early else "fail", 10,
              "" if early else "أول 150 حرف بيظهروا في البحث. حط الكلمة المستهدفة فيهم.")
        count = util.count_phrase(description, keyword)
        if 2 <= count <= 5:
            check("الوصف", f"الكلمة متكررة {count} مرات", "pass", 5)
        elif count == 1:
            check("الوصف", "الكلمة متكررة مرة واحدة", "warn", 5, "كررها مرة أو اتنين كمان بشكل طبيعي.")
        elif count > 5:
            check("الوصف", f"الكلمة متكررة {count} مرات", "warn", 5, "تكرار كتير بيبان حشو. 2-4 مرات كفاية.")
        else:
            check("الوصف", "الكلمة مش موجودة في الوصف", "fail", 5, "اذكر الكلمة المستهدفة في الوصف.")

    n = len(description)
    if n > 5000:
        check("الوصف", f"طول الوصف ({n} حرف)", "fail", 10, "يوتيوب مش بيقبل أكتر من 5000 حرف.")
    elif n >= 250:
        check("الوصف", f"طول الوصف ({n} حرف)", "pass", 10)
    elif n >= 100:
        check("الوصف", f"طول الوصف ({n} حرف)", "warn", 10, "اكتب وصف أطول (250 حرف على الأقل) يشرح الفيديو بكلماتك.")
    else:
        check("الوصف", f"طول الوصف ({n} حرف)", "fail", 10, "الوصف قصير جدًا. يوتيوب بيفهم الفيديو من الوصف.")

    stamps = TIMESTAMP.findall(description)
    starts_at_zero = bool(re.search(r"^\s*\(?0?0:00", description, re.M))
    if len(stamps) >= 3 and starts_at_zero:
        check("الوصف", f"الفصول (Chapters): {len(stamps)}", "pass", 10)
    elif stamps:
        check("الوصف", "الفصول (Chapters)", "warn", 10, "عشان يوتيوب يعمل Chapters: أول توقيت لازم يبقى 0:00، و3 فصول على الأقل.")
    else:
        check("الوصف", "الفصول (Chapters)", "fail", 10, "ضيف توقيتات للفصول. بتظهر في البحث وبتزود وقت المشاهدة.")

    hashtags = HASHTAG.findall(description)
    if 1 <= len(hashtags) <= 3:
        check("الوصف", f"هاشتاجات ({len(hashtags)})", "pass", 5)
    elif not hashtags:
        check("الوصف", "مفيش هاشتاجات", "warn", 5, "ضيف 1-3 هاشتاجات. أول 3 بيظهروا فوق العنوان.")
    elif len(hashtags) <= 15:
        check("الوصف", f"هاشتاجات ({len(hashtags)})", "warn", 5, "أول 3 بس اللي بيظهروا فوق العنوان.")
    else:
        check("الوصف", f"هاشتاجات ({len(hashtags)})", "fail", 5, "أكتر من 15 هاشتاج = يوتيوب بيتجاهلهم كلهم.")

    # ----- tags -----
    total = tags_length(tags)
    if total > 500:
        check("التاجز", f"طول التاجز ({total}/500)", "fail", 5, "يوتيوب مش بيقبل أكتر من 500 حرف تاجز.")
    elif tags:
        check("التاجز", f"طول التاجز ({total}/500)", "pass", 5)
    else:
        check("التاجز", "مفيش تاجز", "fail", 5, "التاجز تأثيرها صغير، بس مفيدة للأخطاء الإملائية والأسماء الإنجليزي.")

    if keyword and tags:
        exact = any(util.normalize(t) == util.normalize(keyword) for t in tags)
        first = util.normalize(tags[0]) == util.normalize(keyword)
        status = "pass" if first else "warn" if exact else "fail"
        tip = "" if first else "خلّي الكلمة المستهدفة أول تاج." if exact else "ضيف الكلمة المستهدفة كتاج بالظبط، وخليها الأول."
        check("التاجز", "الكلمة المستهدفة كتاج", status, 10, tip)

    if 5 <= len(tags) <= 15:
        check("التاجز", f"عدد التاجز ({len(tags)})", "pass", 5)
    elif tags:
        tip = "ضيف تاجز تانية قريبة من الموضوع." if len(tags) < 5 else "تاجز كتير ملهاش لازمة. ركّز على الأهم."
        check("التاجز", f"عدد التاجز ({len(tags)})", "warn", 5, tip)

    possible = sum(c["points"] for c in checks)
    earned = sum(c["earned"] for c in checks)
    return {
        "score": round(earned / possible * 100) if possible else 0,
        "checks": checks,
        "needs_keyword": not keyword,
        "counts": {"title": len(title), "description": len(description), "tags": total},
    }
