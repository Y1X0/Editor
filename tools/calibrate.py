#!/usr/bin/env python3
"""
شبكات معايرة — **أداة، مش كود إنتاج**.

بتطلّع **نفس الإطار** من لقطتك بقيم مختلفة لمُعامل واحد، مركّبة بصورة
وحدة معنونة، عشان الحكم يصير بالعين.

الأرقام اللي بتنعاير هون كلها من صنف واحد: **ما بتنقاس، بتنشاف.**
`npl` سطوع، `crop_bias` تأطير، `size`/`max_words` مقروئية،
`min_gap` إيقاع. ولا واحد فيهن إله جواب صحيح عام — كلهن بيعتمدوا على
وجهك وصوتك وتأطيرك.

    python tools/calibrate.py in.MOV -o out/calib
    python tools/calibrate.py in.MOV -o out/calib --only npl
"""
import argparse
import copy
import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from autoreel import captions as CAP, cuts as C, exports as X, graph as G  # noqa: E402
from autoreel import transcribe as T  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --------------------------------------------------------------- تركيب

def _label(img, text, h=34):
    """شريط عنوان فوق الصورة. لاتيني عمدًا — الاسم مُعامل مش نص عربي."""
    out = Image.new("RGB", (img.width, img.height + h), (18, 18, 20))
    out.paste(img, (0, h))
    d = ImageDraw.Draw(out)
    try:
        f = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
    except OSError:
        f = ImageFont.load_default()
    d.text((8, h // 2), text, font=f, fill=(255, 255, 255), anchor="lm")
    return out


def grid(paths, labels, out_png, cell_w=300):
    """صف أفقي من الصور، كل وحدة معنونة."""
    cells = []
    for p, lb in zip(paths, labels):
        im = Image.open(p).convert("RGB")
        im = im.resize((cell_w, max(1, round(im.height * cell_w / im.width))))
        cells.append(_label(im, lb))
    h = max(c.height for c in cells)
    sheet = Image.new("RGB", (sum(c.width + 6 for c in cells) - 6, h), (18, 18, 20))
    x = 0
    for c in cells:
        sheet.paste(c, (x, 0))
        x += c.width + 6
    sheet.save(out_png)
    return out_png


# ------------------------------------------------------------ المُعاملات

def _frame_through(src, cfg, colors, at, out_png, w, h):
    """إطار واحد عبر الجذع + سلسلة المقاس الحقيقيين."""
    tm = G.tonemap_chain(colors,
                         npl=cfg.get("geometry", {}).get("tonemap_npl", G.DEFAULT_NPL),
                         op=cfg.get("geometry", {}).get("tonemap", G.DEFAULT_TONEMAP))
    chain = G.size_chain(cfg, [1], [1.0], "v0", "vout", w, h)
    pre = f"[0:v]{tm}[v0];" if tm else "[0:v]null[v0];"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{at:.3f}", "-i", str(src),
                    "-filter_complex", pre + chain, "-map", "[vout]",
                    "-frames:v", "1", out_png], check=True)
    return out_png


def sweep_npl(src, root, colors, at, w, h, outdir):
    """سطوع الـtonemap. **بيلزم مصدر HDR** — بغيره ما في سلسلة أصلًا."""
    if not colors.get("hdr"):
        return None, "المصدر مش HDR — ولا سلسلة tonemap، فما في شي يتعاير."
    vals = [400, 700, 1000, 1500, 2200]
    cfg = X.resolve(root, "reel")
    ps, ls = [], []
    for v in vals:
        c = copy.deepcopy(cfg)
        c.setdefault("geometry", {})["tonemap_npl"] = v
        ps.append(_frame_through(src, c, colors, at,
                                 f"{outdir}/_npl{v}.png", w, h))
        ls.append(f"npl={v}")
    return grid(ps, ls, f"{outdir}/1-npl.png"), (
        "أقل npl = أفتح. ١٠٠٠ هي القيمة الاسمية لـHLG مش معايَرة.")


def sweep_crop_bias(src, root, colors, at, w, h, outdir):
    """ارتفاع نافذة القص. أصغر = النافذة بتطلع لفوق."""
    vals = [0.15, 0.22, 0.30, 0.40, 0.50]
    cfg = X.resolve(root, "square")     # القصّ الأحدّ، فالفرق أوضح
    ps, ls = [], []
    for v in vals:
        c = copy.deepcopy(cfg)
        c.setdefault("geometry", {})["crop_bias"] = v
        ps.append(_frame_through(src, c, colors, at,
                                 f"{outdir}/_cb{v}.png", w, h))
        ls.append(f"crop_bias={v}")
    return grid(ps, ls, f"{outdir}/2-crop_bias.png"), (
        "على square (أحدّ قصّ). أصغر = لفوق. شوف أعلى الرأس مش المركز.")


def _caption_png(root, size_name, text, size, outdir, tag):
    cfg = X.resolve(root, size_name)
    ccfg = dict(cfg["captions"])
    ccfg["size"] = size
    ccfg["font"] = os.path.join(ROOT, ccfg["font"])
    W = cfg["output"]["width"]
    img = CAP.render_caption(text, ccfg, W, highlight_idx=1)
    p = f"{outdir}/_cap{tag}.png"
    img.convert("RGB").save(p)
    return p


def sweep_caption_size(root, words, outdir):
    """حجم الخط. النص من كلامك الحقيقي مش من عيّنة."""
    text = " ".join(w["word"] for w in words[:4]) or "كلمة تانية تالتة رابعة"
    vals = [56, 66, 74, 84, 96]
    ps = [_caption_png(root, "reel", text, v, outdir, v) for v in vals]
    return grid(ps, [f"size={v}" for v in vals], f"{outdir}/3-caption_size.png",
                cell_w=360), (
        "على reel بنصّك. اقرأه من مسافة ذراع — هيك بينتشاف على الموبايل.")


def sweep_max_words(root, words, outdir):
    """كلمات الكابشن الواحد."""
    cfg = X.resolve(root, "reel")
    ps, ls = [], []
    for n in (2, 3, 4, 5):
        g = CAP.group_words(words, n)
        text = " ".join(g[0]["words"]) if g else "كلمة تانية"
        ps.append(_caption_png(root, "reel", text, cfg["captions"]["size"],
                               outdir, f"mw{n}"))
        ls.append(f"max_words={n} ({len(g)} كابشن)")
    return grid(ps, ls, f"{outdir}/4-max_words.png", cell_w=360), (
        "أكتر كلمات = كابشنات أقل بس أصغر خطًا (`_fit` بتصغّر لتسع).")


def report_min_gap(words, dur, root, fps):
    """إيقاع — رقم مش صورة. الحكم على عدد المقاطع ومتوسط طولها."""
    lines = ["min_gap | مقاطع | متوسط الطول | انشال"]
    lines.append("--------|-------|-------------|-------")
    for v in (0.25, 0.35, 0.45, 0.60, 0.80):
        cuts = dict(root["cuts"]); cuts["min_gap"] = v
        segs = C.segments_from_words(words, dur, **cuts)
        kept = sum(b - a for a, b in segs)
        avg = kept / len(segs) if segs else 0
        lines.append(f"{v:<7} | {len(segs):<5} | {avg:>11.2f}s | {dur-kept:>5.2f}s")
    return "\n".join(lines)


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(description="شبكات معايرة بالعين")
    ap.add_argument("input")
    ap.add_argument("-o", "--outdir", default="out/calib")
    ap.add_argument("-c", "--config", default="config.json")
    ap.add_argument("--srt", help="بدل Whisper")
    ap.add_argument("--at", type=float, default=None)
    ap.add_argument("--only", help="npl | crop_bias | caption_size | max_words | min_gap")
    a = ap.parse_args()

    root = json.load(open(a.config, encoding="utf-8"))
    os.makedirs(a.outdir, exist_ok=True)
    fps = root["output"]["fps"]

    w, h, _, dur, colors = C.probe(a.input)
    C.verify_source(a.input, w, h)
    at = a.at if a.at is not None else dur / 2

    words = (T.from_srt(a.srt) if a.srt else
             T.transcribe(a.input, root["whisper_model"], root["language"],
                          cache=T.cache_path(a.input, root["whisper_model"],
                                             root["language"])))
    segs = C.segments_from_words(words, dur, **root["cuts"])
    durations = [n / fps for n in C.frame_plan(segs, fps)]
    w2 = C.remap_words(words, segs, durations=durations)

    print(f"المصدر {w}×{h} · hdr={colors['hdr']} · {len(words)} كلمة · "
          f"الإطار عند {at:.2f}s\n")

    todo = {
        "npl": lambda: sweep_npl(a.input, root, colors, at, w, h, a.outdir),
        "crop_bias": lambda: sweep_crop_bias(a.input, root, colors, at, w, h, a.outdir),
        "caption_size": lambda: sweep_caption_size(root, w2 or words, a.outdir),
        "max_words": lambda: sweep_max_words(root, w2 or words, a.outdir),
    }
    for name, fn in todo.items():
        if a.only and a.only != name:
            continue
        p, note = fn()
        print(f"[{name}] {p or 'تخطّي'}\n    {note}\n")

    if not a.only or a.only == "min_gap":
        txt = report_min_gap(words, dur, root, fps)
        open(f"{a.outdir}/5-min_gap.txt", "w", encoding="utf-8").write(txt)
        print("[min_gap] إيقاع — رقم مش صورة:\n" + txt + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
