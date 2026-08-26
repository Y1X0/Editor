"""تفريغ صوتي بتوقيت لكل كلمة (faster-whisper)."""
import os, json


def cache_path(video_path, model_size, language):
    """
    مسار كاش التفريغ.

    الموديل واللغة **جزء من الاسم**: قبل هيك كان المفتاح مسار الملف بس،
    فتغيير `whisper_model` أو `language` بالconfig بيرجّع تفريغ قديم
    بصمت وأنت مستني نتيجة الموديل الجديد.
    """
    return f"{os.path.splitext(video_path)[0]}.{model_size}.{language}.words.json"


def transcribe(path, model_size="small", language="ar", cache=None):
    if cache and os.path.exists(cache):
        return json.load(open(cache, encoding="utf-8"))
    from faster_whisper import WhisperModel
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(path, language=language,
                                   word_timestamps=True, vad_filter=True)
    words = []
    for seg in segments:
        for w in (seg.words or []):
            t = w.word.strip()
            if t:
                words.append({"word": t, "start": float(w.start), "end": float(w.end)})
    if cache:
        json.dump(words, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
    return words


_TS = None


def from_srt(path):
    """
    بديل: لو عندك ملف SRT جاهز بدل ما تشغّل Whisper.

    بنقسّم على السطر الفاضي **قبل** ما نقرا أي كتلة، بدل regex وحدة
    بتمتد عبر الملف كله. الشكل القديم كان بيعتمد على `(?=\\n\\n|\\Z)`
    لتحديد نهاية النص، فكتلة نصها فاضي بتبلع سطر الرقم وسطر التوقيت
    للكتلة الجاية ويصيروا "كلمات" (`2`, `00:00:02,000`, `-->`) —
    بيدخلوا بالكابشن وبخطة القص كمان.
    """
    import re
    global _TS
    if _TS is None:
        _TS = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*"
                         r"(\d+):(\d+):(\d+)[,.](\d+)")

    txt = open(path, encoding="utf-8").read()
    out = []
    for block in re.split(r"\n[ \t]*\n", txt):
        lines = block.splitlines()
        m = i = None
        for i, ln in enumerate(lines):
            m = _TS.search(ln)
            if m:
                break
        if not m:
            continue                      # كتلة بلا سطر توقيت — تجاهلها
        g = m.groups()
        s = int(g[0])*3600 + int(g[1])*60 + int(g[2]) + int(g[3])/1000
        e = int(g[4])*3600 + int(g[5])*60 + int(g[6]) + int(g[7])/1000
        ws = " ".join(lines[i+1:]).split()
        if not ws or e <= s:
            continue                      # بلا نص أو مدة غير صالحة
        step = (e - s) / len(ws)
        for j, w in enumerate(ws):
            out.append({"word": w, "start": s+j*step, "end": s+(j+1)*step})
    return out
