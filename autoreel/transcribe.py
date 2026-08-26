"""تفريغ صوتي بتوقيت لكل كلمة (faster-whisper)."""
import os, json


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


def from_srt(path):
    """بديل: لو عندك ملف SRT جاهز بدل ما تشغّل Whisper."""
    import re
    txt = open(path, encoding="utf-8").read()
    out = []
    for m in re.finditer(
        r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)\s*\n(.+?)(?=\n\n|\Z)",
        txt, re.S):
        g = m.groups()
        s = int(g[0])*3600+int(g[1])*60+int(g[2])+int(g[3])/1000
        e = int(g[4])*3600+int(g[5])*60+int(g[6])+int(g[7])/1000
        ws = g[8].replace("\n", " ").split()
        if not ws:
            continue
        step = (e - s) / len(ws)
        for i, w in enumerate(ws):
            out.append({"word": w, "start": s+i*step, "end": s+(i+1)*step})
    return out
