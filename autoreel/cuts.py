"""بناء خطة القص من توقيتات الكلمات (أدق من silencedetect لفيديو الكلام)."""
import subprocess, re


# أدنى نسخة ffmpeg **مفحوصة**. أقل منها ما بتنمنع — بس بيطلع تحذير،
# لأن ما بنقدر نعد بشي ما قِسناه.
#
# الحادثة اللي فرضت الفحص: كل أرقام المشروع مقاسة على 7.0.2، وطلع إن
# `amix=duration=first` بتعطي **١٢٨٠ عيّنة أقل** على 6.1.1 — الصوت
# بينقصّ ٢٦.٧ms بصمت والأداة بتقول "تمّ بنجاح". الطول انتثبّت بالبناء
# بعدها (`graph.sfx_chain`)، بس الدرس أعمّ: **ادعاء "٧٤١ فحص أخضر"
# بلا ذكر النسخة ادعاء ناقص.**
VERIFIED_FFMPEG = (7, 0)
MIN_FFMPEG = (6, 0)


def ffmpeg_version():
    """`(major, minor)` من `ffmpeg -version`، أو `None` لو ما انقرا."""
    r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
    m = re.search(r"ffmpeg version n?(\d+)\.(\d+)", r.stdout)
    return (int(m.group(1)), int(m.group(2))) if m else None


def check_ffmpeg(warn=None):
    """
    بيتحقّق من نسخة ffmpeg. بيرجّع النسخة، وبيحذّر لو أقل من المفحوصة.

    بيرمي لو أقل من `MIN_FFMPEG` — تحت هيك في فلاتر منعتمد عليها
    ممكن ما تكون موجودة أصلًا، والفشل الصريح أوضح من مخرَج غريب.
    """
    v = ffmpeg_version()
    if v is None:
        return None
    if v < MIN_FFMPEG:
        raise RuntimeError(
            f"ffmpeg {v[0]}.{v[1]} قديم جدًا — الحدّ الأدنى "
            f"{MIN_FFMPEG[0]}.{MIN_FFMPEG[1]}")
    if v < VERIFIED_FFMPEG and warn:
        warn(f"⚠️  ffmpeg {v[0]}.{v[1]} — كل أرقام المشروع مقاسة على "
             f"{VERIFIED_FFMPEG[0]}.{VERIFIED_FFMPEG[1]}+. "
             f"المسار بيشتغل، بس السلوك تحتها غير متحقَّق منه.")
    return v


# الدوال الانتقالية اللي معناها HDR. `arib-std-b67` هي HLG — وهاي
# **الحالة الافتراضية للآيفون**، مش حالة نادرة.
HDR_TRC = ("arib-std-b67", "smpte2084")


def _colors(banner):
    """
    وسوم الألوان من سطر التيار بـ`ffmpeg -i`. ولا نداء إضافي.

    الشكل: `yuv420p10le(tv, bt2020nc/bt2020/arib-std-b67, progressive)`
    وبمصدر SDR بسيط بيصير `yuv420p` بلا قوسين إطلاقًا — فكل الحقول
    بترجع `None` وهاد المقصود: «ما بنعرف» غير «bt709».
    """
    m = re.search(r": Video:.*?, (\w+)(?:\(([^)]*)\))?", banner)
    if not m:
        return {"pix_fmt": None, "range": None, "primaries": None,
                "matrix": None, "trc": None, "hdr": False, "bits": None}
    pix = m.group(1)
    bits = 10 if "10" in pix else (12 if "12" in pix else 8)
    fields = [f.strip() for f in (m.group(2) or "").split(",")]
    rng = fields[0] if fields and fields[0] in ("tv", "pc") else None
    # `bt2020nc/bt2020/arib-std-b67` = مصفوفة/أوّليات/دالة انتقالية.
    # وبتطلع كمان بشكل حقل واحد (`bt709`) لما التلاتة متطابقة.
    trio = next((f for f in fields if "/" in f), None)
    one = next((f for f in fields
                if f and f not in ("tv", "pc", "progressive") and "/" not in f), None)
    if trio:
        parts = trio.split("/")
        matrix, prim, trc = (parts + [None, None, None])[:3]
    else:
        matrix = prim = trc = one
    return {"pix_fmt": pix, "range": rng, "primaries": prim, "matrix": matrix,
            "trc": trc, "hdr": trc in HDR_TRC, "bits": bits}


def _rotation_swaps_wh(banner):
    """
    هل مصفوفة الدوران بتقلب العرض والارتفاع؟

    الآيفون بيسجّل أفقيًا وبيحط مصفوفة دوران، وffmpeg **بيدوّر تلقائيًا
    عند الفكّ**. فسطر `Stream` بيعطي الحجم المرمَّز (١٩٢٠×١٠٨٠) بينما
    اللي بيوصل رسم الفلاتر معروضًا (١٠٨٠×١٩٢٠).

    القياس على الأربع حالات (`-display_rotation` عند البناء):

        90        -> `rotation of 90.00 degrees`     -> قلب
        180       -> `rotation of -180.00 degrees`   -> بلا قلب
        270 / -90 -> `rotation of -90.00 degrees`    -> قلب

    **الإشارة مش معلومة مفيدة:** ffmpeg بيطبّع الزاوية لـ(-180, 180]،
    فـ`270` و`-90` بيطلعوا نفس السطر بالضبط. القرار على `abs` وبس.
    """
    m = re.search(r"displaymatrix: rotation of (-?[\d.]+) degrees", banner)
    return bool(m) and round(abs(float(m.group(1)))) % 180 == 90


def probe(path):
    """
    `(عرض, ارتفاع, فيه_صوت, مدة, ألوان)` بنداء `ffmpeg -i` **واحد**.

    **الأبعاد معروضة مش مرمَّزة** — شوف `_rotation_swaps_wh`.
    `graph.size_chain` بتبني نافذة القص من أرقام بايثون (لأن `crop.iw`
    ما بتتتبّع مقاسًا متغيّرًا)، فالرقم غير المطبَّع كان بيعطي نافذة من
    مكان غلط **بلا ما تفشل**.

    `ألوان` انضافت **بالآخر** عمدًا: `probe_source` بتاخد `[:3]` و
    `probe_duration` بتاخد `[3]`، فالتوسيع ما بيكسر ولا مستدعي.

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
    colors = _colors(r.stderr)
    w, h = int(m.group(1)), int(m.group(2))
    if _rotation_swaps_wh(r.stderr):
        w, h = h, w

    d = re.search(r"Duration: (\d+):(\d\d):(\d\d(?:\.\d+)?)", r.stderr)
    if not d:
        # `Duration: N/A` بتطلع لتيار حي أو ملف مقصوص — وأي رقم
        # منخترعه هون بينتشر لخطة القص كلها. الفشل أوضح.
        raise RuntimeError(f"ما قدرت أقرا مدة {path} — `ffmpeg -i` ما أعطى مدة")
    dur = int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3))
    return w, h, has_audio, dur, colors


def probe_duration(path):
    """مدة المصدر بالثواني. شوف `probe` — التقريب لجزء المئة موثّق هناك."""
    return probe(path)[3]


# `0:1` = SAR غير محدَّد، وffmpeg بيعامله ١:١. **ولقطات الآيفون بتعطيه**
# — فحص بيقارن بـ`1:1` وبس كان رح يرمي على كل ملف منها.
OK_SAR = ("1:1", "0:1")


def delivered(path):
    """
    الأبعاد وSAR اللي ffmpeg **بيسلّمها فعلًا** لرسم الفلاتر.

    `showinfo` على إطار واحد. الكلفة مقاسة: ٢١.٦ms مقابل ٥.٥ms لـ
    `ffmpeg -i`، وكلاهما لا شي جنب دقايق الترميز.
    """
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(path), "-vf", "showinfo",
         "-frames:v", "1", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"\bs:(\d+)x(\d+)", r.stderr)
    if not m:
        raise RuntimeError(f"ما قدرت أقرا أبعاد الإطار المسلَّم من {path}")
    s = re.search(r"\bsar:(\d+)/(\d+)", r.stderr)
    return (int(m.group(1)), int(m.group(2)),
            f"{s.group(1)}:{s.group(2)}" if s else None)


def verify_source(path, w, h, warn=None):
    """
    **افحص الفرضية مش الحالة.**

    حارس على «الدوران متصلّح» بيحمي من حالة وحدة. هاد بيفحص الفرضية
    نفسها: الأبعاد اللي `graph` رح تبني عليها تعابيرها لازم تطابق
    اللي ffmpeg رح يسلّمه. فبيمسك الدوران، و`SAR` مش مربّعة، والقصّ
    بالحاوية، وأي سلوك جديد بنسخة ffmpeg جاية — بلا ما نعرفهن سلفًا.

    **بيرمي ما بيحذّر.** التحذير بيضيع بين أسطر تقدّم ffmpeg والمستخدم
    بيشوف `✅ خلص` بالآخر؛ والتصليح التلقائي أسوأ لأنه بيخفي إن
    فرضيتنا كانت غلط.
    """
    dw, dh, sar = delivered(path)
    if (w, h) != (dw, dh):
        raise RuntimeError(
            f"فرضية مكسورة عن {path}:\n"
            f"    الهندسة محسوبة على  {w}×{h}\n"
            f"    وffmpeg بيسلّم       {dw}×{dh}\n"
            f"    نافذة القص رح تطلع من مكان غلط بلا ما تفشل. "
            f"شوف SOURCE-SPEC.md.")
    if sar is not None and sar not in OK_SAR:
        raise RuntimeError(
            f"SAR = {sar} على {path} — بكسل غير مربّع.\n"
            f"    `size_chain` بتشتغل على أبعاد التخزين وبتتجاهل SAR، "
            f"فالصورة بتنضغط. مش مدعوم.")
    return dw, dh, sar


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

