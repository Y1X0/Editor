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


def estimate_gain(with_sfx, without_sfx, touched=(), sr=SR, floor=0.05):
    """
    كسب الكلام الفعلي بالمخرَج، مقيسًا من المخرَج نفسه.

    **ليش بينقاس مش بينفترض:** الرسم بيطلب `volume=0.70`، بس الواصل
    فعليًا `0.4950 = 0.70 × 1/√2` لمصدر **مونو** — تحويل مونو->ستيريو
    جوّا الرسم بيضيف ١/√٢ (حفظ طاقة). لمصدر ستيريو ما في تحويل
    فالكسب ٠.٧٠. يعني الرقم بيعتمد على شكل المصدر، فافتراضه غلط.

    الوسيط على السعات الكبيرة: تكميم ١٦ بت بيخرّب النسب الصغيرة
    (مقيس: مدى ١.٦e−٢ عند |x|>٠.٠٠١ مقابل ٢e−٤ عند |x|>٠.٠٥).
    """
    a, b = pcm(without_sfx, sr), pcm(with_sfx, sr)
    skip = set(touched)
    r = sorted(b[i] / a[i] for i in range(min(len(a), len(b)))
               if i not in skip and abs(a[i]) > floor)
    if not r:
        return 1.0
    return r[len(r) // 2]


def difference(with_sfx, without_sfx, sr=SR, gain=1.0):
    """
    إشارة المؤثرات لحالها = |مع − كسب×بدون|.

    **`gain` مش زينة.** الكلام بينضرب بثابت لما تنمزج المؤثرات
    (§الهامش)، فطرح خام بيخلّي فرق الكلام بالإشارة — والكاشف بيمسك
    نقرات المصدر كأنها مؤثرات. صار معنا: ٢٧ نبضة مكتشفة مقابل ٨
    مؤثرات، والزيادة كلها عند مضاعفات ٢٤٠٠٠ عيّنة = نقرات المصدر
    كل نص ثانية.
    """
    a, b = pcm(without_sfx, sr), pcm(with_sfx, sr)
    n = min(len(a), len(b))
    return [abs(b[i] - gain * a[i]) for i in range(n)]


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


def onset_in_window(diff, start, length, ratio=0.35, lead=64):
    """
    بداية المؤثر **داخل نافذته** — مش من قائمة نبضات عامة.

    ليش النافذة: العدّ العام بينكسر مرّتين. الأصول الصاعدة
    (`whoosh`/`riser`) بتعبر العتبة مرارًا لأن غلافها بيصعد وينزل،
    و`impact` منخفض التردد (٨١Hz) فدوراته بتتباعد أكتر من فترة
    الكبت (٢٤٠٠ عيّنة) وبيتعدّ ٣ مرات. مقيس: ٧ نبضات لـ٥ مؤثرات.

    بالنافذة السؤال بيصير محدَّدًا: **وين بلّش هالمؤثر بالذات؟**
    بترجّع فهرس أول عيّنة توصل `ratio` من قمة النافذة، أو `None`.
    """
    lo = max(0, start - lead)
    hi = min(len(diff), start + length)
    win = diff[lo:hi]
    if not win:
        return None
    peak = max(win)
    if peak <= 0:
        return None
    t = peak * ratio
    for i, v in enumerate(win):
        if v >= t:
            return lo + i
    return None


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
