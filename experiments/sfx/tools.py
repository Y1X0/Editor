"""أدوات قياس للـSFX. مستقلة عن كود الإنتاج."""
import struct, subprocess, wave, os

SR = 48000


def run(args, **kw):
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + args,
                       capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-1500:])
    return r


def pcm(path):
    """عيّنات mono float من ملف — بفكّ لـwav 48k mono."""
    tmp = path + ".probe.wav"
    run(["-i", path, "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", tmp])
    with wave.open(tmp) as w:
        n = w.getnframes()
        raw = w.readframes(n)
    os.remove(tmp)
    return [v / 32768.0 for v in struct.unpack(f"<{n}h", raw)]


def impulses(samples, thresh_ratio=0.35, refractory=2400):
    """
    مواقع النبضات بالعيّنة. عتبة **نسبية** لقمة الإشارة — العتبة
    المطلقة كانت أصل فشل قياس بمرحلة سابقة (٠ نبضات من ٢٠).
    """
    peak = max((abs(v) for v in samples), default=0.0)
    if peak == 0:
        return []
    t = peak * thresh_ratio
    out, last = [], -10**9
    for i, v in enumerate(samples):
        if abs(v) >= t and i - last > refractory:
            out.append(i)
            last = i
    return out


def click(path, dur=0.02, freq=2000, sr=SR):
    """SFX اختبار: نبضة قصيرة حادة البداية."""
    run(["-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate={sr}:duration={dur}",
         "-c:a", "pcm_s16le", path])
    return path


def silence(path, dur, sr=SR, ch=1):
    run(["-f", "lavfi", "-i",
         f"anullsrc=sample_rate={sr}:channel_layout={'mono' if ch==1 else 'stereo'}",
         "-t", str(dur), "-c:a", "pcm_s16le", path])
    return path
