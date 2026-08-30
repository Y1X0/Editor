"""`Timeline` + العقود ──► تشغيلة ffmpeg **واحدة** ──► `out.mp4`.

آخر مرحلة بالمسار، وأضيقها مسؤولية. الراسم **ما بيقرّر شي**: كل رقم
بيدخل تعبير فلتر بيجي من عقد انتحدّد قبله.

    Timeline      عدد الإطارات · حدود المقاطع · `asset_in_frame`
    AssetsContract  الملف · `fit` · `motion`
    SegmentsContract  النص العربي (من المصدر، §19)
    TypographyContract  الحجم · اللون لكل مقطع
    Output        الأبعاد · fps · معدل العيّنات

**اللي هالموديول ممنوع يعمله — والقائمة جزء من العقد:**

  · ما بيحسب مدة. `audio_duration` انقيست عند نقطة الدخول ودخلت
    `quantize`، و`total_frames` جاهزة بالـtimeline. الراسم ما بيسأل
    الملف عن طوله، وما بيعمل probe للصوت.
  · ما بيعدّل الـtimeline. بيقرا منه وبس.
  · ما بينادي نموذجًا ولا resolver.
  · **ما بيعيد المحاولة.** ffmpeg بيفشل -> `FfmpegError` وخلص. إعادة
    محاولة على ترميز فاشل بتخبّي السبب وبتاكل دقايق.

**والفصل بين النقيّ والمشغِّل مقصود:** `build_command()` دالة نقية
بترجّع قائمة الوسائط، و`render()` بتشغّلها. هيك بينفحص شكل الأمر بلا
ترميز — نفس اللي بيخلي `autoreel.render` قابلة للاختبار أصلًا.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageFilter

from shared.captions import render_caption
from shared.ffmpeg import exe
from shared.frames import caption_sequence

from .models.alignment import Alignment

from .errors import ContractError, FfmpegError
from .models.assets import AssetsContract
from .models.project import Output
from .models.segments import SegmentsContract
from .models.timeline import Timeline
from .models.typography import TypographyContract

#: عامل التكبير لكل قيمة `motion`، و**إزاحة المرساة** أفقيًا كنسبة من
#: الفائض بعد القصّ (0.5 = موسّط).
#:
#: **ثابت داخل المقطع، مش متحركًا** — نفس قرار المحرر الموثَّق
#: بـ`CLAUDE.md`: «الزوم ثابت داخل المقطع مش zoompan متحرك — هيك الشكل
#: المعروف بالريلز، وأخف على المعالج». فـ`pan_left` بتختار **تأطيرًا**
#: من يسار الإطار، مش حركة عبره. إسقاط القيمة بصمت كان بيصير
#: `motion.pan_px` تاني: حقل بالعقد وما إله أثر بالمخرَج.
MOTION: dict[str, tuple[float, float]] = {
    "none":       (1.00, 0.5),
    "zoom_in":    (1.08, 0.5),
    "zoom_out":   (1.05, 0.5),
    "pan_left":   (1.05, 0.0),
    "pan_right":  (1.05, 1.0),
}


@dataclass(frozen=True)
class CaptionStyle:
    """القيم اللي **مش** بعقد Phase 1 — الخط والصندوق وارتفاع السطر.

    `TypographyContract` بتحمل الحجم واللون لكل مقطع، وما بتحمل مسار
    خط: عقد Phase 1 ما فيه حقل خط، وهاد قرار مقفول (شوف
    `expand_typography_proposal`). فالباقي بيوصل **من المستدعي**، ما
    بينخترع هون.

    ⚠️ الخط مسؤولية المستدعي لأن الـtheme بيملكه: Tajawal ما بترسم
    علامات الوقف ولا الألف الخنجرية، فالنص القرآني عليها بيطلع دوائر
    منقّطة. لكل theme خطّه.
    """

    font: Path
    #: **هالة بدل صندوق.** الصندوق المستطيل بيقصّ التكوين ويبيّن
    #: كقالب؛ الهالة بتيجي من قناة ألفا النص نفسه مموّهة، فبتتبع شكل
    #: الحروف وبتعطي تباينًا بلا حدود صلبة. الرقم نصف قطر التمويه
    #: كنسبة من حجم الخط.
    scrim_radius: float = 0.30
    scrim_alpha: int = 232
    highlight_rgb: tuple[int, int, int] = (255, 214, 130)
    #: ٠.٧٤ بتسيب مساحة كافية فوق واجهة إنستغرام (شوف `CLAUDE.md`).
    y_ratio: float = 0.74
    #: إطارات الانتقال عند بداية كل مقطع. ٩ = ٠.٣s عند 30fps.
    anim_frames: int = 9
    #: إزاحة `fade_in_up` بالبكسل، ومدى `fade_in_scale`.
    rise_px: int = 34
    scale_from: float = 0.86
    #: تلوين الكلمة المنطوقة. بيحتاج `alignment` — بلاها بينطفي لحاله.
    karaoke: bool = True


@dataclass(frozen=True)
class Encode:
    """إعدادات المرمِّز. مجموعة هون عشان الأمر يضل قابلًا للمقارنة."""

    vcodec: str = "libx264"
    preset: str = "medium"
    crf: int = 20
    pix_fmt: str = "yuv420p"
    acodec: str = "aac"
    abitrate: str = "192k"
    extra: tuple[str, ...] = field(default=("-movflags", "+faststart"))


# ── الكابشن ──────────────────────────────────────────────────────────
def word_frames(alignment: Alignment, timeline: Timeline,
                segments: SegmentsContract) -> dict[int, list[tuple[int, int]]]:
    """`{segment_id: [(إطار_البداية, فهرس_الكلمة_داخل_المقطع)]}`.

    **الكلمة بتضل ملوّنة لحد بداية اللي بعدها، مش لحد نهايتها هي.**
    قرار موثَّق بالمحرر ومقيس عليه: Whisper بيرجّع فراغًا صغيرًا بين كل
    كلمتين، والإنهاء عند `end` بيخلّي الكابشن يرفرف بنص الجملة
    (التغطية ٦٣٪ -> ٨١٪).

    الحدود **مقصوصة على الـspan النصّي** تبع الـtimeline، فالسلطة على
    بداية المقطع ونهايته تضل هناك — وعليه فحص بيقارن الطرفين.
    """
    fps = timeline.fps
    spans = {sp.segment_id: sp for sp in timeline.text_spans}
    out: dict[int, list[tuple[int, int]]] = {}
    for seg in segments.segments:
        sp = spans.get(seg.segment_id)
        if sp is None:
            continue
        marks: list[tuple[int, int]] = []
        for k, w in enumerate(alignment.words[seg.word_start:seg.word_end]):
            f = max(sp.f_start, min(round(w.start * fps), sp.f_end - 1))
            if marks and f <= marks[-1][0]:
                continue                    # كلمتان بنفس الإطار: الأولى بتغلب
            marks.append((f, k))
        if not marks:
            marks = [(sp.f_start, 0)]
        marks[0] = (sp.f_start, marks[0][1])   # أول كلمة بتبلّش مع المقطع
        out[seg.segment_id] = marks
    return out


def _scrim(img: "Image.Image", size: int, style: CaptionStyle) -> "Image.Image":
    """هالة داكنة مشتقّة من ألفا النص نفسه.

    **بديل الصندوق المستطيل.** الصندوق بيبيّن كقالب وبيقصّ التكوين؛
    الهالة بتتبع شكل الحروف، فبتعطي التباين اللازم للقراءة على خلفية
    فاتحة بلا حدّ صلب. مقيس بهالمستودع إن النص بلا أي خلفية بيعطي نسبة
    تباين 1.06 على لقطة فاتحة — غير مرئي عمليًا.
    """
    r = max(2, int(size * style.scrim_radius))
    halo = img.split()[3].filter(ImageFilter.GaussianBlur(r))
    halo = halo.point(lambda v: min(255, int(v * 3.1)))
    dark = Image.new("RGBA", img.size, (0, 0, 0, 0))
    dark.putalpha(halo.point(lambda v: v * style.scrim_alpha // 255))
    out = Image.alpha_composite(dark, img)
    return out


def _place(base: "Image.Image", canvas: tuple[int, int],
           dy: int = 0, scale: float = 1.0, alpha: float = 1.0):
    """بيحطّ الصورة بلوحة ثابتة المقاس مع إزاحة/تحجيم/شفافية.

    **اللوحة ثابتة بقصد**: مُدخل تسلسل الصور بياخد الأبعاد من أول ملف،
    وأي اختلاف بعده بيقطع المخرَج بصمت — ٤٠٧×٢٠٨ مقابل ٤٠٨×٢٠٨ أعطت
    ٧٣ إطار من ١٤٤. فالحركة بتصير **جوّا** اللوحة، لا بتغيّر مقاسها.
    """
    im = base
    if scale != 1.0:
        w, h = max(1, int(base.width * scale)), max(1, int(base.height * scale))
        im = base.resize((w, h), Image.LANCZOS)
    if alpha < 1.0:
        a = im.split()[3].point(lambda v: int(v * alpha))
        im = im.copy()
        im.putalpha(a)
    out = Image.new("RGBA", canvas, (0, 0, 0, 0))
    out.paste(im, ((canvas[0] - im.width) // 2,
                   (canvas[1] - im.height) // 2 + dy), im)
    return out


def rasterise_captions(
    timeline: Timeline, segments: SegmentsContract,
    typo: TypographyContract, output: Output, style: CaptionStyle,
    workdir: str | Path, alignment: Alignment | None = None,
) -> str:
    """بيرجّع نمط `…/%06d.png` جاهز لـ`-framerate FPS -start_number 0`.

    **صورة لكل إطار**، مش لكل مقطع: الحركة والكاريوكي بيغيّروا الشكل
    جوّا المقطع. التكرار بينمسك بذاكرة مؤقتة على المفتاح
    `(مقطع, كلمة, خطوة الحركة)`، فعدد الملفات المميّزة بيضل بالعشرات.

    خريطة إطار->صورة من `shared.frames.caption_sequence` — القاعدة
    بتيجي من `shared`، والكتابة بس هون.
    """
    work = Path(workdir)
    png_dir, seq_dir = work / "png", work / "seq"
    for d in (png_dir, seq_dir):
        d.mkdir(parents=True, exist_ok=True)

    by_id = {s.segment_id: s for s in segments.segments}
    anim_of = {t.segment_id: t.animation for t in typo.segments}
    marks = (word_frames(alignment, timeline, segments)
             if (alignment is not None and style.karaoke) else {})

    # ① الصور الأساسية: نسخة لكل كلمة مُبرَزة (أو وحدة بلا إبراز)
    base: dict[tuple[int, int], "Image.Image"] = {}
    sizes: dict[int, int] = {}
    for sp in timeline.text_spans:
        seg = by_id.get(sp.segment_id)
        if seg is None:
            raise ContractError(
                f"مقطع {sp.segment_id}: span نصّي بلا مقطع بـsegments.json")
        ov = typo.overrides.get(sp.segment_id)
        if ov is None or ov.font_size is None or ov.text_color is None:
            raise ContractError(
                f"مقطع {sp.segment_id}: ما في حجم/لون بالـtypography — "
                f"الراسم ما بيخترع قيمة ناقصة")
        cfg = {"font": str(style.font), "size": ov.font_size,
               "color": list(bytes.fromhex(ov.text_color[1:])),
               "highlight": list(style.highlight_rgb),
               "box": [0, 0, 0, 0],          # ولا صندوق — الهالة بديله
               "y_ratio": style.y_ratio}
        sizes[sp.segment_id] = ov.font_size
        idxs = ([k for _, k in marks[sp.segment_id]]
                if sp.segment_id in marks else [None])
        for k in idxs:
            img = render_caption(seg.text_arabic, cfg, output.width,
                                 highlight_idx=k).convert("RGBA")
            base[(sp.segment_id, -1 if k is None else k)] = _scrim(
                img, ov.font_size, style)

    if not base:
        raise ContractError("ولا كابشن — `text_spans` فاضية")

    # ② لوحة واحدة لكل التسلسل، بهامش يسع إزاحة الحركة
    cw = max(i.width for i in base.values())
    ch = max(i.height for i in base.values()) + 2 * style.rise_px
    canvas = (cw + (cw % 2), ch + (ch % 2))

    # ③ إطار إطار، مع ذاكرة على (مقطع, كلمة, خطوة)
    cache: dict[tuple, str] = {}
    frames: list[tuple[str, int, int]] = []
    for sp in timeline.text_spans:
        anim = anim_of.get(sp.segment_id, "none")
        m = marks.get(sp.segment_id)
        for n in range(sp.f_start, sp.f_end):
            k = -1
            if m:
                k = next(idx for f, idx in reversed(m) if f <= n)
            step = n - sp.f_start
            phase = step if step < style.anim_frames and anim != "none" else -1
            key = (sp.segment_id, k, phase)
            if key not in cache:
                t = 1.0 if phase < 0 else (phase + 1) / style.anim_frames
                dy = sc = 0
                a = t if phase >= 0 else 1.0
                dy = int(style.rise_px * (1 - t)) if anim == "fade_in_up" else 0
                sc = (style.scale_from + (1 - style.scale_from) * t
                      if anim == "fade_in_scale" else 1.0)
                path = png_dir / f"{sp.segment_id:02d}_{k+1:02d}_{phase+1:02d}.png"
                _place(base[(sp.segment_id, k)], canvas,
                       dy=dy, scale=sc, alpha=a).save(path)
                cache[key] = str(path)
            frames.append((cache[key], n, n + 1))

    seq = caption_sequence(frames, timeline.total_frames)
    blank = png_dir / "blank.png"
    if any(p is None for p in seq):
        Image.new("RGBA", canvas, (0, 0, 0, 0)).save(blank)

    use_symlink = True
    for n, png in enumerate(seq):
        dst = seq_dir / f"{n:06d}.png"
        # **الحذف قبل الكتابة إلزامي.** تشغيلة تانية على نفس مجلّد
        # العمل بتلاقي وصلة قديمة، فـ`symlink` بترمي، والسقوط للنسخ
        # بيصير نسخ ملف على نفسه (`SameFileError`). مقيس: أول إعادة
        # رسم بلا مسح يدوي بتنفجر.
        dst.unlink(missing_ok=True)
        target = os.path.abspath(png if png is not None else blank)
        if use_symlink:
            try:
                os.symlink(target, dst)
                continue
            except (OSError, NotImplementedError, AttributeError):
                use_symlink = False      # نظام ملفات ما بيدعمها — كمّل نسخًا
        shutil.copy2(target, dst)
    return str(seq_dir / "%06d.png")


# ── الأمر: دالة نقية ─────────────────────────────────────────────────
def _even(n: float) -> int:
    return (int(n) // 2) * 2


def video_chain(k: int, span, asset, output: Output, fps: int) -> str:
    """سلسلة مقطع واحد. **`trim` بفهرس الإطار مش بالثواني.**

    الترتيب مقصود ومطبَّق مرتين بهالمستودع: `fps=` **قبل** أي قصّ، وإلا
    الفهرس بينحسب على معدل المصدر مش على معدل المخرَج.
    """
    zoom, anchor = MOTION[asset.motion]
    w, h = output.width, output.height
    tw, th = _even(w * zoom), _even(h * zoom)
    if asset.fit == "cover":
        # يغطّي الإطار ثم يُقصّ — ولا بكسل خلفية.
        geom = (f"scale={tw}:{th}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h}:x=(iw-{w})*{anchor}:y=(ih-{h})/2")
    else:
        # `contain`: يسع كاملًا ثم يُبطَّن — ولا بكسل مقصوص.
        geom = (f"scale={tw}:{th}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)*{anchor}:(oh-ih)/2:color=black")
    return (f"[{k}:v]fps={fps},{geom},setsar=1,"
            f"trim=start_frame=0:end_frame={span.n_frames},"
            f"setpts=PTS-STARTPTS[v{k}]")


def build_command(
    timeline: Timeline, assets: AssetsContract, output: Output,
    audio: str | Path, caption_pattern: str, out_path: str | Path, *,
    y_ratio: float, encode: Encode = Encode(),
) -> list[str]:
    """أمر ffmpeg كامل. **نقية: ولا قراءة قرص ولا تشغيل.**

    ترتيب المدخلات جزء من العقد: مقطع لكل span بصري بالترتيب، بعدها
    تسلسل الكابشن، بعده الصوت. الفهارس بالفلاتر مبنية عليه.
    """
    fps, spans = timeline.fps, timeline.visual_spans
    cmd = [exe(), "-hide_banner", "-y"]
    chains, labels = [], []

    for k, sp in enumerate(spans):
        try:
            a = assets.by_segment(sp.segment_id)
        except KeyError:
            raise ContractError(
                f"مقطع {sp.segment_id}: span بصري بلا أصل بـassets.json"
            ) from None
        # **الفهرس من الـtimeline، مش من `asset.in_point`.** الاتنان
        # بيتّفقوا لما `quantize` تبنيهن سوا، بس السلطة على اللي
        # بينرمّز هي الـtimeline — وغيابه فشل، مش صفرًا افتراضيًا.
        if sp.segment_id not in timeline.asset_in_frame:
            raise ContractError(
                f"مقطع {sp.segment_id}: ما في `asset_in_frame` — الراسم "
                f"ما بيفترض البداية من الإطار صفر")
        ss = timeline.asset_in_frame[sp.segment_id] / fps
        cmd += ["-ss", f"{ss:.6f}", "-i", str(a.file_path)]
        chains.append(video_chain(k, sp, a, output, fps))
        labels.append(f"[v{k}]")

    n = len(spans)
    cmd += ["-framerate", str(fps), "-start_number", "0", "-i", caption_pattern]
    cmd += ["-i", str(audio)]

    chains.append("".join(labels) + f"concat=n={n}:v=1:a=0[vcat]")
    chains.append(f"[vcat][{n}:v]overlay=x=(W-w)/2:"
                  f"y=(H*{y_ratio})-h/2:eof_action=pass[vout]")
    # **الطول مثبَّت بالبناء، مش متروكًا لـ`-shortest`.** حادثة موثَّقة
    # بهالمستودع: `amix=duration=first` بتحسب الطول غير بين ffmpeg 6.x
    # و7.x (فرق ١٢٨٠ عيّنة). `apad,atrim=end_sample=N` بتشيل الفرق أصلًا.
    chains.append(f"[{n + 1}:a]aresample={timeline.sample_rate},apad,"
                  f"atrim=end_sample={timeline.total_samples}[aout]")

    cmd += ["-filter_complex", ";".join(chains),
            "-map", "[vout]", "-map", "[aout]",
            "-frames:v", str(timeline.total_frames),
            "-c:v", encode.vcodec, "-preset", encode.preset,
            "-crf", str(encode.crf), "-pix_fmt", encode.pix_fmt,
            "-r", str(fps),
            "-c:a", encode.acodec, "-b:a", encode.abitrate,
            "-ar", str(timeline.sample_rate),
            *encode.extra, str(out_path)]
    return cmd


# ── التشغيل ──────────────────────────────────────────────────────────
def render(
    timeline: Timeline, segments: SegmentsContract, assets: AssetsContract,
    typo: TypographyContract, output: Output, *,
    audio: str | Path, out_path: str | Path, workdir: str | Path,
    style: CaptionStyle, alignment: Alignment | None = None,
    encode: Encode = Encode(), dry_run: bool = False,
) -> list[str]:
    """بيرسم ويرجّع الأمر اللي انشغّل (أو اللي **كان** بينشغّل).

    `dry_run` بيوقف قبل ffmpeg وبعد رسم الكابشن: التسلسل بينكتب فعلًا،
    فالمطبوع هو الأمر الحقيقي مش تقريبًا إله.
    """
    pattern = rasterise_captions(timeline, segments, typo, output, style,
                                 workdir, alignment=alignment)
    # `y_ratio` بيمرق **كوسيط**: الرسم بيوسّط الكابشن داخل صندوق موحّد
    # والoverlay بيوسّط الصندوق عند هالارتفاع، فالقيمتان لازم تكونا
    # نفسها. تمريرها بيخلّي `build_command` نقيّة وقابلة لإعادة الدخول.
    cmd = build_command(timeline, assets, output, audio, pattern, out_path,
                        y_ratio=style.y_ratio, encode=encode)
    if dry_run:
        return cmd

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        # **ولا إعادة محاولة.** ffmpeg اللي بيفشل مرة بيفشل تانية على
        # نفس المدخلات، والإعادة بتخبّي السطر اللي بيقول ليش.
        tail = "\n".join(r.stderr.strip().splitlines()[-12:])
        raise FfmpegError(f"ffmpeg رجع {r.returncode}:\n{tail}")
    return cmd
