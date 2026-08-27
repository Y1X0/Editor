"""بناء خطة القص من توقيتات الكلمات (أدق من silencedetect لفيديو الكلام)."""
import subprocess, re


def probe(path):
    """
    `(عرض, ارتفاع, فيه_صوت, مدة)` بنداء `ffmpeg -i` **واحد**.

    **ولا اعتماد على `ffprobe`.** كان `probe_duration` بتناديه بينما
    `probe_source` بتتجنّبه صراحة — فالتجنّب كان نصّ تجنّب، وأول سطر
    بالمسار كان بينهار على أي تثبيت static (وهاد شكل التثبيت الشائع
    على Termux، وهو حال بيئة التطوير عنا):

        FileNotFoundError: [Errno 2] No such file or directory: 'ffprobe'

    ولا فحص مسكها لأن كل فحص بيمرق على المسار كان بيبدّل
    `probe_duration` — الفحص اللي بيبدّل الجزء المكسور ما بيشوف الكسر.
    الحارس هلأ `tests/test_probe.py` وبينادي المسار **بلا تبديل**.

    ⚠️ **المدة مقرَّبة لجزء المئة من الثانية، وهاد حدّ من ffmpeg مش
    اختيارًا منّا.** سطر `Duration: HH:MM:SS.ss` هو أدقّ شي بيطلّعه
    `ffmpeg -i` بأي `-loglevel` (فحصناهن كلهن)، بينما `ffprobe` كان
    بيعطي ميكروثانية. الفرق ≤ ٥ms. البدائل انقاست وانرفضت:

    | البديل | الفرق عن `ffprobe` |
    |---|---|
    | `Duration:` من stderr | **≤ ٥ms** ← المختار |
    | `-progress` + `out_time_us` | لحد ١٨٦ms — بيقيس نهاية أطول تيار مش مدة الحاوية |
    | `-map 0 -c copy` + `-progress` | نفسها، ١٨٦ms |

    **وين بتوصل هالـ٥ms:** `duration` بتدخل بتلات أماكن بس — `--no-cut`
    (الفيديو كله مقطع واحد)، ولا كلمات أصلًا، وحدّ `min(duration,
    prev_end + pad)` اللي بيشتغل بس لما آخر كلمة تخلص على بعد أقل من
    `pad` من نهاية الملف. بالمسار المعتاد (قص شغّال وفيه كلمات) ما إلها
    أثر. بالحالات التلاتة بتغيّر `frame_plan` **بإطار واحد** لـ٨.٢٥٪ من
    المدد عند ٣٠fps (مسح ٢٠٠ ألف مدة). مش خطأ بأي اتجاه — الاتنين قراءة
    صحيحة لمدة الحاوية، وE1 (المخرَج = الخطة) بيضل صحيحًا بالحالتين.
    """
    r = subprocess.run(["ffmpeg", "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Stream #\d+:\d+.*?: Video:.*?, (\d+)x(\d+)", r.stderr)
    if not m:
        raise RuntimeError(f"ما قدرت أقرا أبعاد الفيديو من {path}")
    has_audio = re.search(r"Stream #\d+:\d+.*?: Audio:", r.stderr) is not None

    d = re.search(r"Duration: (\d+):(\d\d):(\d\d(?:\.\d+)?)", r.stderr)
    if not d:
        # `Duration: N/A` بتطلع لتيار حي أو ملف مقصوص — وأي رقم
        # منخترعه هون بينتشر لخطة القص كلها. الفشل أوضح.
        raise RuntimeError(f"ما قدرت أقرا مدة {path} — `ffmpeg -i` ما أعطى مدة")
    dur = int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3))
    return int(m.group(1)), int(m.group(2)), has_audio, dur


def probe_duration(path):
    """مدة المصدر بالثواني. شوف `probe` — التقريب لجزء المئة موثّق هناك."""
    return probe(path)[3]


def segments_from_words(words, duration, min_gap=0.45, pad=0.10, min_seg=0.35):
    """
    يرجّع مقاطع الكلام بعد شيل الصمت الطويل.
    min_gap: أي فراغ أطول من هيك بينشال.
    pad: هامش أمان قبل وبعد كل مقطع حتى ما تنقص أول/آخر حرف.
    """
    if not words:
        return [(0.0, duration)]
    segs = []
    s = max(0.0, words[0]["start"] - pad)
    prev_end = words[0]["end"]
    for w in words[1:]:
        if w["start"] - prev_end > min_gap:
            segs.append((s, min(duration, prev_end + pad)))
            s = max(0.0, w["start"] - pad)
        prev_end = w["end"]
    segs.append((s, min(duration, prev_end + pad)))

    merged = []
    for a, b in segs:
        if b - a < min_seg:
            continue
        if merged and a - merged[-1][1] < 0.06:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return merged or [(0.0, duration)]


def remap_words(words, segs, min_ratio=0.45, durations=None):
    """
    بعد القص بتتغير التوقيتات. هاي بترجّع الكلمات بتوقيت الفيديو الجديد،
    وبتشيل الكلمات اللي وقعت جوا الأجزاء المحذوفة.

    `min_ratio`: أقل نسبة من مدة الكلمة لازم تنجى من القص حتى تضل.
    بتنحسب **تراكميًا عبر كل المقاطع**، مش لكل مقطع لحاله.

    `durations`: المدة **الفعلية** لكل مقطع بعد الترميز (من
    `frame_plan`، يعني `N/fps`). بدونها بنستعمل `b-a` وهاد بيفترض إن
    ffmpeg بيرمّز المدة المطلوبة بالضبط — وهو ما بيعملها. النتيجة إن
    الكابشن بينزاح عن الصورة بمقدار بيتراكم مع كل مقطع.
    """
    if durations is None:
        durations = [b - a for a, b in segs]
    # تمريرة أولى للمجموع. القياس لكل مقطع لحاله كان بيرمي كلمة موزّعة
    # ٤٣٪/٢٩٪ على مقطعين رغم إنها ٧٢٪ حاضرة — وهي بالضبط حالة الكلمة
    # اللي على حد القص اللي العتبة موجودة عشان تحميها.
    kept = []
    for w in words:
        ov = sum(max(0.0, min(w["end"], b) - max(w["start"], a)) for a, b in segs)
        kept.append(ov / max(1e-6, w["end"] - w["start"]) >= min_ratio)

    out, offset, prev_i = [], 0.0, None
    for (a, b), seg_dur in zip(segs, durations):
        # المقطع بينرمّز بمدة `seg_dur` مش `b-a`. الكلمة جوا المقطع
        # بتنقص لهالمدة، وإلا كابشن آخر كلمة بيمتد برّا المقطع.
        scale = seg_dur / max(1e-9, b - a)
        for i, w in enumerate(words):
            # تداخل جزئي كافي — مش شرط الكلمة تكون كاملة جوا المقطع،
            # وإلا بتضيع الكلمات اللي على حدود القص.
            if not kept[i] or min(w["end"], b) - max(w["start"], a) <= 0:
                continue
            s = (max(w["start"], a) - a) * scale + offset
            e = (min(w["end"], b) - a) * scale + offset
            # نفس الكلمة المصدرية انقسمت بين مقطعين -> مدّدها بدل ما
            # تكرّرها. المقارنة بالفهرس مش بالنص: «لا لا» كلمتين
            # حقيقيتين، والمقارنة النصية كانت بتصهرهن بوحدة.
            #
            # الفهرس كافي لحاله: الكلمة الواحدة بتنبعث مرة لكل مقطع،
            # والمقاطع مرتّبة، فتكرار الفهرس ورا بعض معناه حدود قص
            # بالضبط — ما بصير جوا نفس المقطع.
            if out and prev_i == i:
                out[-1]["end"] = e
            else:
                out.append({"word": w["word"], "start": s, "end": e})
            prev_i = i
        offset += seg_dur
    return out


def frame_plan(segs, fps):
    """
    عدد الإطارات لكل مقطع — الوحدة اللي بتحكم التوقيت فعليًا.

    **ليش الإطارات مش الثواني:** ffmpeg ما بيضمن مدة المقطع لما تعطيه
    أزمانًا. قياس على ٥ مقاطع (المطلوب 7.428s):

        -ss a -to b            -> 226 إطار = 7.533s   (+112ms)
        تقريب -ss/-to للشبكة   -> 222 إطار = 7.400s   (−28ms)
        -ss a + -frames:v N    -> 223 إطار = 7.433s   (+5ms)

    تقريب الأزمان بيقلب الخطأ من زيادة لنقصان بس ما بيصفّره — لأن
    القرار النهائي لعدد الإطارات عند ffmpeg مش عنا. `-frames:v N`
    بينقل القرار لعنا: N إطار بالضبط، و`concat -c copy` بيحافظ على
    المجموع (متحقَّق: 223 = 223).

    فالتوقيت الجديد للكابشن بينبني من الإطارات التراكمية، وبهيك
    الخطة والمرمَّز بيتفقوا **بالتعريف** مش بالتقريب.
    """
    return [max(1, round((b - a) * fps)) for a, b in segs]


def dropped_words(words, segs, min_ratio=0.45):
    """
    الكلمات اللي ما بتنجو من القص، بترتيبها الأصلي.

    نفس قاعدة `remap_words` بالضبط عشان ما تفترقوا: كلمة بتنشال إما
    لأن مقطعها انحذف (`min_seg` بتشيل المقاطع القصيرة بصمت) أو لأن
    تداخلها التراكمي تحت العتبة.
    """
    out = []
    for w in words:
        ov = sum(max(0.0, min(w["end"], b) - max(w["start"], a)) for a, b in segs)
        if ov / max(1e-6, w["end"] - w["start"]) < min_ratio:
            out.append(w["word"])
    return out


def total_after_cut(segs):
    return sum(b - a for a, b in segs)

