"""مجلّد أصول ──► `catalog.json` جاهز للـResolver.

```bash
python tools/build_catalog.py assets/ -o catalog.json
```

بيمشي على المجلّد، بيقيس كل ملف بـffmpeg، بيحسب بصمته، وبيكتب صفًّا
بالكتالوج. **والصور بتنتحوّل للقطات متحرّكة** بزحف بطيء — فصورة
مولَّدة بالذكاء الاصطناعي بتصير خلفية شغّالة بلا ما تصوّر شي.

الكلمات المفتاحية بتنقرا من **اسم الملف**: `dark-night-calm.jpg` بتعطي
`["dark","night","calm"]`. وهاد مقصود — الوكيل البصري بيبحث بكلمات،
والاسم هو أرخص مكان يكتب فيه صاحب المكتبة وصفَه.

⚠️ **أداة مساعدة، برّا الحزمة.** المسار ما بينادي هالملف: الكتالوج
مُدخَل موثوق بالنسبة إله، وبناؤه قرار بشري. وهي كمان **ما بتحمّل ولا
ملف من الإنترنت** — الشبكة قرار منفصل وسطح خطر منفصل.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.ffmpeg import exe                                   # noqa: E402

VIDEO = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
IMAGE = {".jpg", ".jpeg", ".png", ".webp"}

_V = re.compile(r"Video: .*?, (\d+)x(\d+)")
_F = re.compile(r",\s*([\d.]+) fps")
_D = re.compile(r"Duration: (\d+):(\d+):(\d+\.\d+)")

#: مفردات العقد المغلقة — أي قيمة برّاها بيرفضها `CatalogEntry`.
SHOTS = ("wide", "medium", "macro", "aerial", "abstract")
PALETTES = ("charcoal", "deep_blue", "warm_gold", "monochrome")


def probe(p: Path) -> dict:
    info = subprocess.run([exe(), "-hide_banner", "-i", str(p)],
                          capture_output=True, text=True).stderr
    v, f, d = _V.search(info), _F.search(info), _D.search(info)
    if not v:
        raise SystemExit(f"{p}: ولا تيار فيديو — تخطّاه أو شيله")
    h, m, s = d.groups() if d else ("0", "0", "0.0")
    return {"width": int(v.group(1)), "height": int(v.group(2)),
            "fps": float(f.group(1)) if f else 30.0,
            "duration": int(h) * 3600 + int(m) * 60 + float(s)}


def bottom_scrim(w: int, h: int, dst: Path, start: float = 0.52,
                 peak: int = 190) -> Path:
    """تدرّج داكن بأسفل الإطار — **حتى يُقرأ الكابشن على أي لقطة**.

    الهالة حوالين الحروف بتكفّي على خلفية هادئة وبتفشل على صورة
    مصوّرة مزدحمة: الحروف بتلاقي حافة أو تباينًا عاليًا تحتها.
    التدرّج بيعطي أرضية ثابتة بلا حدّ صلب ظاهر.

    مخبوز **بالأصل** لا مضافًا وقت الرندر: بيكلّف صفرًا بكل تشغيلة،
    وبينطبّق على اللقطات الحقيقية بنفس الأداة.
    """
    from PIL import Image                                       # noqa: PLC0415
    g = Image.new("L", (1, h), 0)
    px = g.load()
    for y in range(h):
        t = (y / (h - 1) - start) / (1 - start)
        px[0, y] = 0 if t <= 0 else int(peak * t ** 1.7)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    layer.putalpha(g.resize((w, h)))
    layer.save(dst)
    return dst


def animate(src: Path, dst: Path, seconds: float, fps: int, size: str) -> None:
    """صورة ثابتة ──► لقطة عمودية بزحف بطيء.

    **الحركة بتنخبز بالأصل مش بالراسم** — الراسم بيثبّت الزوم داخل
    المقطع بقرار موثَّق («الزوم ثابت داخل المقطع مش zoompan متحرك»).
    فالزحف المستمر مكانه هون، والقاعدة هناك تضل كما هي.

    **وتعبئة مموّهة بدل القصّ**، لأن مصدر الصور المولَّدة غالبًا مربّع
    أو 3:4: القصّ لـ9:16 بياكل نصّ الصورة وبيشيل موضوعها. النسخة
    المموّهة بتملا الإطار والنسخة الحادّة بتقعد فوقها كاملة —
    فولا بكسل من الموضوع بيضيع.
    """
    w, h = (int(x) for x in size.split("x"))
    bw, bh = w * 3 // 2, h * 3 // 2          # غرفة للزحف
    n = int(seconds * fps)
    scrim = dst.with_suffix(".scrim.png")
    bottom_scrim(w, h, scrim)
    chain = (
        f"[0:v]scale={bw}:{bh}:force_original_aspect_ratio=increase,"
        f"crop={bw}:{bh},gblur=sigma=42,eq=brightness=-0.16:saturation=0.85[bg];"
        f"[0:v]scale={bw}:{bh}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        f"zoompan=z='1.00+0.09*on/{n}':"
        f"x='iw/2-(iw/zoom/2)+(on-{n // 2})*0.08':"
        f"y='ih/2-(ih/zoom/2)':d={n}:s={w}x{h}:fps={fps}[kb];"
        f"[kb][1:v]overlay=0:0[o]")
    subprocess.run([
        exe(), "-v", "error", "-loop", "1", "-i", str(src),
        "-loop", "1", "-i", str(scrim),
        "-filter_complex", chain, "-map", "[o]",
        "-frames:v", str(n), "-r", str(fps), "-pix_fmt", "yuv420p",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-an",
        "-y", str(dst)], check=True)
    scrim.unlink(missing_ok=True)


def keywords_of(name: str) -> list[str]:
    parts = re.split(r"[-_\s.]+", name.lower())
    return [p for p in parts if p.isalpha() and len(p) > 2][:8]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=Path("catalog.json"))
    ap.add_argument("--shot", default="abstract", choices=SHOTS,
                    help="نوع اللقطة الافتراضي لكل صفّ")
    ap.add_argument("--palette", default="monochrome", choices=PALETTES)
    ap.add_argument("--license", default="owned",
                    help="الرخصة — **إلزامية بالعقد**، ما في افتراضي فاضي")
    ap.add_argument("--seconds", type=float, default=12.0,
                    help="مدة اللقطة المولَّدة من صورة ثابتة")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--size", default="1080x1920")
    a = ap.parse_args(argv)

    root = a.out.resolve().parent
    clips = root / "clips"
    entries, made = [], 0
    for p in sorted(a.folder.rglob("*")):
        if p.suffix.lower() in IMAGE:
            clips.mkdir(parents=True, exist_ok=True)
            dst = clips / f"{p.stem}.mp4"
            print(f"  صورة -> لقطة: {p.name}", file=sys.stderr)
            animate(p, dst, a.seconds, a.fps, a.size)
            p, made = dst, made + 1
        elif p.suffix.lower() not in VIDEO:
            continue
        try:
            rel = p.resolve().relative_to(root)
        except ValueError:
            raise SystemExit(
                f"{p}: برّا مجلّد الكتالوج — الـResolver بيرفض أي مسار "
                f"بيطلع برّا جذره، فحطّ الأصول جنب `catalog.json`")
        entries.append({
            "provider": "local", "provider_ref": p.stem,
            "path": str(rel), "license": a.license,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "probe": probe(p), "keywords": keywords_of(p.stem),
            "shot_type": a.shot, "palette": a.palette,
            "attribution": None, "source_type": "local"})

    if not entries:
        raise SystemExit(f"ولا أصل بـ{a.folder} — المدعوم: "
                         f"{' '.join(sorted(VIDEO | IMAGE))}")
    a.out.write_text(json.dumps({"entries": entries}, ensure_ascii=False,
                                indent=2) + "\n", encoding="utf-8")
    print(f"\n{a.out}: {len(entries)} أصل ({made} منها من صور ثابتة)")
    print("راجع `keywords` و`shot_type` و`palette` قبل التشغيل — "
          "الوكيل البصري بيبحث فيهن.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
