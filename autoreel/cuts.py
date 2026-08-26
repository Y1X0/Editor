"""بناء خطة القص من توقيتات الكلمات (أدق من silencedetect لفيديو الكلام)."""
import subprocess, json, re


def probe_duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path], capture_output=True, text=True, check=True)
    return float(json.loads(r.stdout)["format"]["duration"])


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


def remap_words(words, segs, min_ratio=0.45):
    """
    بعد القص بتتغير التوقيتات. هاي بترجّع الكلمات بتوقيت الفيديو الجديد،
    وبتشيل الكلمات اللي وقعت جوا الأجزاء المحذوفة.

    `min_ratio`: أقل نسبة من مدة الكلمة لازم تنجى من القص حتى تضل.
    بتنحسب **تراكميًا عبر كل المقاطع**، مش لكل مقطع لحاله.
    """
    # تمريرة أولى للمجموع. القياس لكل مقطع لحاله كان بيرمي كلمة موزّعة
    # ٤٣٪/٢٩٪ على مقطعين رغم إنها ٧٢٪ حاضرة — وهي بالضبط حالة الكلمة
    # اللي على حد القص اللي العتبة موجودة عشان تحميها.
    kept = []
    for w in words:
        ov = sum(max(0.0, min(w["end"], b) - max(w["start"], a)) for a, b in segs)
        kept.append(ov / max(1e-6, w["end"] - w["start"]) >= min_ratio)

    out, offset, prev_i = [], 0.0, None
    for a, b in segs:
        for i, w in enumerate(words):
            # تداخل جزئي كافي — مش شرط الكلمة تكون كاملة جوا المقطع،
            # وإلا بتضيع الكلمات اللي على حدود القص.
            if not kept[i] or min(w["end"], b) - max(w["start"], a) <= 0:
                continue
            s = max(w["start"], a) - a + offset
            e = min(w["end"], b) - a + offset
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
        offset += (b - a)
    return out


def total_after_cut(segs):
    return sum(b - a for a, b in segs)


def parse_silencedetect(path, noise="-32dB", d=0.4):
    """بديل احتياطي لو ما في تفريغ صوتي — كشف صمت مباشر من الصوت."""
    r = subprocess.run(
        ["ffmpeg", "-i", path, "-af", f"silencedetect=noise={noise}:d={d}",
         "-f", "null", "-"], capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    return list(zip(starts, ends))
