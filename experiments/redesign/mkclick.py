"""مصدر اختبار: فيديو ٣٠fps + مسار نقرات حادّة بأزمنة معروفة بالضبط."""
import array, subprocess, os

SR, DUR, FPS = 48000, 40.0, 30
CLICK_EVERY = 0.5
CLICK_MS = 2

n = int(SR * DUR)
a = array.array('h', bytes(2 * n))
t = 0.0
times = []
while t < DUR - 0.1:
    i0 = round(t * SR)
    for j in range(int(SR * CLICK_MS / 1000)):
        a[i0 + j] = 32000 if j % 2 == 0 else -32000   # موجة مربعة قصيرة، طاقة كاملة
    times.append(t)
    t += CLICK_EVERY

open("/tmp/realrun/click.raw", "wb").write(a.tobytes())
open("/tmp/realrun/click_times.txt", "w").write("\n".join(f"{x:.6f}" for x in times))

subprocess.run([
    "ffmpeg", "-y", "-v", "error",
    "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate={FPS}:duration={DUR}",
    "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", "/tmp/realrun/click.raw",
    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-ar", str(SR), "-shortest",
    "/tmp/realrun/click.mp4"], check=True)
print(f"{len(times)} نقرة · {DUR}s · {FPS}fps -> click.mp4")
