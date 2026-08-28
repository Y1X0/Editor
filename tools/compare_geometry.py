#!/usr/bin/env python3
"""
هندسة القص: أرقام `probe` مقابل اللي ffmpeg بيسلّمه — **أداة، مش إنتاج**.

بترسم **نفس الإطار** من المصدر مرتين، بنفس سلسلة `graph.size_chain`
الحقيقية، والفرق الوحيد الأبعاد المُمرَّرة:

    أ) اللي `cuts.probe` بترجّعها اليوم  (الحجم المرمَّز)
    ب) اللي ffmpeg بيسلّمه فعلًا        (بعد الدوران)

**ليش مش مقارنة بمرجع «دوران مخبوز»:** خبز الدوران بيلزمه إعادة ترميز،
وإعادة الترميز لحالها بتضيف ضجيج جيل بيلوّث القياس (قِسناه: ٢٠.٩dB على
مصدر HEVC رغم إن الهندسة متطابقة). هون المتغيّر الوحيد الأرقام، فأي
فرق هو الخلل نفسه بلا وسيط.

    python tools/compare_geometry.py in.MOV -o out/geom --at 4.0
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from autoreel import cuts as C, exports as X, graph as G  # noqa: E402


def delivered_size(path):
    """الأبعاد اللي بتوصل رسم الفلاتر — من `showinfo` على إطار واحد."""
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(path), "-vf", "showinfo",
         "-frames:v", "1", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"\bs:(\d+)x(\d+)", r.stderr)
    if not m:
        raise SystemExit("ما قدرت أقرا أبعاد الإطار من showinfo")
    return int(m.group(1)), int(m.group(2))


def render(src, cfg, w, h, at, out_png):
    """إطار واحد عبر `size_chain` المبنية على `(w, h)`."""
    chain = G.size_chain(cfg, [1], [1.0], "v0", "vout", w, h)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{at:.3f}", "-i", str(src),
         "-filter_complex", f"[0:v]null[v0];{chain}",
         "-map", "[vout]", "-frames:v", "1", out_png], check=True)
    return out_png


def psnr(a, b):
    """`inf` معناها إطاران متطابقان بايت-ببايت."""
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", a, "-i", b,
         "-lavfi", "[0:v][1:v]psnr", "-f", "null", "-"],
        capture_output=True, text=True)
    m = re.search(r"average:([\d.]+|inf)", r.stderr)
    return m.group(1) if m else "?"


def main():
    ap = argparse.ArgumentParser(description="قارن هندسة القص بأرقام probe مقابل الواقع")
    ap.add_argument("input")
    ap.add_argument("-o", "--outdir", default="out/geom")
    ap.add_argument("-c", "--config", default="config.json")
    ap.add_argument("--at", type=float, default=None, help="ثانية الإطار (افتراضي: النص)")
    ap.add_argument("--sizes", default="all")
    args = ap.parse_args()

    root = json.load(open(args.config, encoding="utf-8"))
    os.makedirs(args.outdir, exist_ok=True)

    pw, ph, _, dur = C.probe(args.input)
    dw, dh = delivered_size(args.input)
    at = args.at if args.at is not None else dur / 2

    print(f"probe بترجّع      : {pw}×{ph}")
    print(f"ffmpeg بيسلّم     : {dw}×{dh}")
    print(f"الإطار عند        : {at:.2f}s\n")

    rows = []
    for name in X.select(root, args.sizes):
        cfg = X.resolve(root, name)
        a = render(args.input, cfg, pw, ph, at, f"{args.outdir}/{name}.probe.png")
        b = render(args.input, cfg, dw, dh, at, f"{args.outdir}/{name}.real.png")
        same_graph = (G.size_chain(cfg, [1], [1.0], "v", "o", pw, ph)
                      == G.size_chain(cfg, [1], [1.0], "v", "o", dw, dh))
        p = psnr(a, b)
        rows.append((name, cfg["output"]["width"], cfg["output"]["height"],
                     cfg.get("geometry", {}).get("fit", "crop"), same_graph, p))
        # صورة جنب صورة عشان الحكم بالعين مش بالرقم
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", a, "-i", b, "-lavfi",
             "[0:v]scale=420:-2,pad=iw+8:ih:0:0:color=white[l];"
             "[1:v]scale=420:-2[r];[l][r]hstack",
             f"{args.outdir}/{name}.cmp.png"], check=True)

    w = max(len(r[0]) for r in rows)
    print(f"{'مقاس':<{w}}  {'المقاس':<11} {'fit':<5} {'رسم متطابق':<11} PSNR")
    for name, W, H, fit, same, p in rows:
        print(f"{name:<{w}}  {W}×{H:<7} {fit:<5} "
              f"{'نعم' if same else '**لا**':<11} {p}")
    print(f"\nصور المقارنة بـ{args.outdir}/*.cmp.png  (يسار = أرقام probe · يمين = الواقع)")
    # `inf` بكل صف معناها الخلل ما إله أثر مرئي على هالمصدر — نتيجة
    # صالحة، مش نجاح. الحكم للمواصفة مش لكود الخروج.
    return 0


if __name__ == "__main__":
    sys.exit(main())
