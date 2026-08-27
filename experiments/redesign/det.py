"""كاشف النقرات — بيرجّع زمن **قمة** كل نقرة (أثبت من عتبة الصعود مع AAC)."""
import subprocess, array

SR = 48000


def samples(path):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-ac', '1',
                          '-ar', str(SR), '-f', 's16le', '-'],
                         capture_output=True).stdout
    a = array.array('h')
    a.frombytes(raw)
    return a


def peaks(path, rel=0.35, gap_ms=120):
    """كل عنقود فوق rel من أقصى قيمة -> زمن أعلى عيّنة فيه."""
    a = samples(path)
    if not a:
        return []
    lim = max(abs(v) for v in a) * rel
    out, i, gap = [], 0, int(SR * gap_ms / 1000)
    n = len(a)
    while i < n:
        if abs(a[i]) > lim:
            j, best, bi = i, abs(a[i]), i
            quiet = 0
            while j < n and quiet < gap:
                if abs(a[j]) > lim:
                    quiet = 0
                    if abs(a[j]) > best:
                        best, bi = abs(a[j]), j
                else:
                    quiet += 1
                j += 1
            out.append(bi / SR)
            i = j
        else:
            i += 1
    return out


if __name__ == "__main__":
    want = [float(x) for x in open("/tmp/realrun/click_times.txt").read().split()]
    got = peaks("/tmp/realrun/click.mp4")
    print(f"المرجع: {len(want)} نقرة · وجدنا: {len(got)}")
    n = min(len(want), len(got))
    errs = [(got[i] - want[i]) * 1000 for i in range(n)]
    print(f"انزياح الكاشف على المصدر نفسه: "
          f"أول={errs[0]:+.2f}ms  آخر={errs[-1]:+.2f}ms  "
          f"أقصى={max(abs(e) for e in errs):.2f}ms")
    print("  -> هاي أرضية القياس؛ أي رقم أصغر منها مش ذو دلالة.")
