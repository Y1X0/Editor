#!/usr/bin/env python3
"""
تقرير تشخيصي عن ملف مصدر — **أداة، مش كود إنتاج**.

بيطبع كل شي بيلزم قبل ما تشغّل الأداة على مصدر من صنف جديد: الأبعاد
المرمَّزة مقابل اللي بتوصل الفلاتر، الدوران، الكودك، ملف الألوان،
الصوت، وتفاوت معدل الإطارات **الفعلي** مش المعلَن.

ليش برّا `autoreel/`: ما بينستدعى من المسار، وبيشغّل نداءات ffmpeg
إضافية عمدًا (`showinfo` على عيّنة إطارات) — وهاد مقبول لأداة تشخيص
ومرفوض بالمسار.

    python tools/probe_report.py input.MOV
    python tools/probe_report.py input.MOV --json
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from autoreel import cuts as C  # noqa: E402


def _banner(path):
    return subprocess.run(["ffmpeg", "-i", str(path)],
                          capture_output=True, text=True).stderr


def _showinfo(path, frames):
    """`showinfo` على أول `frames` إطار. بيرجّع (نص stderr)."""
    return subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(path), "-vf", "showinfo",
         "-frames:v", str(frames), "-f", "null", "-"],
        capture_output=True, text=True).stderr


def report(path, frames=120):
    b = _banner(path)
    v = re.search(r"Stream #\d+:\d+.*?: Video: (\w+).*?, (\w+)\(([^)]*)\).*?, "
                  r"(\d+)x(\d+)(?: \[SAR (\d+):(\d+) DAR (\d+):(\d+)\])?", b)
    a = re.search(r"Stream #\d+:\d+.*?: Audio: (\w+).*?, (\d+) Hz, (\w+)", b)
    rot = re.search(r"displaymatrix: rotation of (-?[\d.]+) degrees", b)
    fps = re.search(r", ([\d.]+) fps", b)
    tbr = re.search(r", ([\d.]+) tbr", b)
    dur = re.search(r"Duration: (\d+):(\d\d):(\d\d(?:\.\d+)?)", b)

    si = _showinfo(path, frames)
    real = re.search(r"\bs:(\d+)x(\d+)", si)
    sar = re.search(r"\bsar:(\d+)/(\d+)", si)
    times = [float(t) for t in re.findall(r"pts_time:([\d.]+)", si)]
    gaps = [round((times[i + 1] - times[i]) * 1000, 2)
            for i in range(len(times) - 1)]

    angle = float(rot.group(1)) if rot else 0.0
    out = {
        "path": str(path),
        "ffmpeg": ".".join(map(str, C.ffmpeg_version() or ())) or "?",
        "video_codec": v.group(1) if v else None,
        "pix_fmt": v.group(2) if v else None,
        "color": (v.group(3) if v else "") or None,
        "coded_size": [int(v.group(4)), int(v.group(5))] if v else None,
        "delivered_size": [int(real.group(1)), int(real.group(2))] if real else None,
        "sar": f"{sar.group(1)}:{sar.group(2)}" if sar else None,
        "rotation": angle,
        "rotation_swaps_wh": round(abs(angle)) % 180 == 90,
        "declared_fps": float(fps.group(1)) if fps else None,
        "tbr": float(tbr.group(1)) if tbr else None,
        "duration": (int(dur.group(1)) * 3600 + int(dur.group(2)) * 60
                     + float(dur.group(3))) if dur else None,
        "audio_codec": a.group(1) if a else None,
        "audio_sr": int(a.group(2)) if a else None,
        "audio_layout": a.group(3) if a else None,
        "gap_ms_min": min(gaps) if gaps else None,
        "gap_ms_max": max(gaps) if gaps else None,
        "gap_ms_distinct": sorted(set(gaps))[:8] if gaps else [],
        "is_vfr": len(set(gaps)) > 1 if gaps else None,
        "frames_sampled": len(times),
    }
    out["probe_returns"] = list(C.probe(path)[:2])
    out["probe_matches_reality"] = out["probe_returns"] == out["delivered_size"]
    return out


def render(r):
    L = []
    w = L.append
    w(f"# تقرير المصدر — {os.path.basename(r['path'])}")
    w(f"\n_ffmpeg {r['ffmpeg']}_\n")
    w("| | |")
    w("|---|---|")
    w(f"| الكودك | `{r['video_codec']}` · `{r['pix_fmt']}` |")
    w(f"| ملف الألوان | `{r['color']}` |")
    w(f"| الحجم المرمَّز | **{r['coded_size'][0]}×{r['coded_size'][1]}** |")
    w(f"| اللي بيوصل الفلاتر | **{r['delivered_size'][0]}×{r['delivered_size'][1]}** |")
    w(f"| SAR | `{r['sar']}` |")
    w(f"| مصفوفة دوران | **{r['rotation']}°**"
      f"{' — بتقلب w/h' if r['rotation_swaps_wh'] else ''} |")
    w(f"| fps معلَن / tbr | {r['declared_fps']} / {r['tbr']} |")
    w(f"| المدة | {r['duration']}s |")
    w(f"| الصوت | `{r['audio_codec']}` · {r['audio_sr']} Hz · {r['audio_layout']} |")
    w(f"| تفاوت الإطارات (ms) | {r['gap_ms_min']} – {r['gap_ms_max']} "
      f"على {r['frames_sampled']} إطار |")
    w(f"| VFR؟ | {'**نعم**' if r['is_vfr'] else 'لأ (ثابت)'} "
      f"· فروقات مميّزة: `{r['gap_ms_distinct']}` |")
    w("")
    ok = r["probe_matches_reality"]
    w(f"## `cuts.probe` بترجّع `{tuple(r['probe_returns'])}` — "
      f"{'✅ مطابق للواقع' if ok else '❌ **مخالف للواقع**'}")
    if not ok:
        w("")
        w(f"> الهندسة بتنحسب على `{tuple(r['probe_returns'])}` بينما ffmpeg "
          f"بيسلّم `{tuple(r['delivered_size'])}`. نافذة القص رح تطلع من مكان "
          f"غلط **بلا ما تفشل**. شوف `SOURCE-SPEC.md`.")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="تقرير تشخيصي عن ملف مصدر")
    ap.add_argument("input")
    ap.add_argument("--frames", type=int, default=120,
                    help="كم إطار ينفحص لقياس تفاوت المعدل")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    r = report(args.input, args.frames)
    print(json.dumps(r, ensure_ascii=False, indent=2) if args.json else render(r))
    # كود الخروج **مش** فشلًا: التقرير تشخيص، والحكم للمواصفة.
    return 0


if __name__ == "__main__":
    sys.exit(main())
