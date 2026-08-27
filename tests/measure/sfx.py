"""
أدوات قياس المؤثرات الصوتية.

**الفكرة المركزية:** قياس المؤثر بيصير بالفرق بين تشغيلتين — وحدة
بمؤثرات ووحدة بدونهن. الفرق بين المخرَجين هو **إشارة المؤثر لحالها**،
معزولة عن الكلام تمامًا.

ليش مش كشف مباشر على المخرَج النهائي: كاشف النبضات عتبته نسبية لقمة
الإشارة، والكلام أعلى من المؤثر بكتير. تشغيله على مخرَج فيه كلام
بيخلّيه يمسك الكلام نفسه ويرجّع مواقع بلا معنى — قِسناها: −٢٣٩٨٤
عيّنة. الطرح بيشيل الكلام من المعادلة أصلًا.
"""
import os
import struct
import subprocess
import wave

SR = 48000
ASSET_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "assets", "sfx")
ASSETS = ("tick", "pop", "whoosh", "impact", "riser")


def asset(name):
    return os.path.join(ASSET_DIR, f"{name}.wav")


def pcm(path, sr=SR):
    """عيّنات mono float — بفكّ لـwav بمعدّل معروف."""
    tmp = f"{path}.sfxprobe.wav"
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path),
                        "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", tmp],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ما قدرت أفكّ {path}:\n{r.stderr[-600:]}")
    try:
        with wave.open(tmp) as w:
            n = w.getnframes()
            raw = w.readframes(n)
    finally:
        os.remove(tmp)
    return [v / 32768.0 for v in struct.unpack(f"<{n}h", raw)]


def wav_info(path):
    """`(قنوات, بت, معدّل, إطارات)` من ترويسة WAV مباشرة — بلا ffmpeg."""
    with wave.open(str(path)) as w:
        return w.getnchannels(), w.getsampwidth() * 8, w.getframerate(), w.getnframes()


def difference(with_sfx, without_sfx, sr=SR):
    """إشارة المؤثرات لحالها = |مع − بدون|، عيّنة بعيّنة."""
    a, b = pcm(without_sfx, sr), pcm(with_sfx, sr)
    n = min(len(a), len(b))
    return [abs(b[i] - a[i]) for i in range(n)]


def hits(diff, ratio=0.35, refractory=2400):
    """
    مواقع المؤثرات بالعيّنة من إشارة الفرق.

    العتبة **نسبية** لقمة الفرق. `refractory` بيمنع عدّ نفس المؤثر
    مرتين (المؤثر إله ذيل، مش نبضة وحدة).
    """
    peak = max(diff, default=0.0)
    if peak <= 0:
        return []
    t = peak * ratio
    out, last = [], -10 ** 9
    for i, v in enumerate(diff):
        if v >= t and i - last > refractory:
            out.append(i)
            last = i
    return out


def frame_to_sample(frame, fps, sr=SR):
    """نفس التحويل اللي المواصفة بتفرضه — ضرب صحيح، بلا تقريب."""
    assert sr % fps == 0, f"{sr} مش قابلة للقسمة على {fps}"
    return frame * (sr // fps)


def clipped(path, sr=SR, limit=0.999):
    return sum(1 for v in pcm(path, sr) if abs(v) >= limit)


def peak_of(path, sr=SR):
    s = pcm(path, sr)
    return max((abs(v) for v in s), default=0.0)


def detector_floor(name="pop"):
    """
    أرضية الكاشف: كم عيّنة بيتأخّر عن البداية الحقيقية للمؤثر.

    المؤثر بيوصل العتبة بعد شوية عيّنات من بدايته، فالقياس بيطلع
    متأخّرًا بمقدار ثابت. بينطرح من كل نتيجة — بدونه كل الأرقام
    بتبيّن منزاحة وهي مضبوطة.
    """
    s = pcm(asset(name))
    peak = max(abs(v) for v in s)
    for i, v in enumerate(s):
        if abs(v) >= peak * 0.35:
            return i
    return 0
