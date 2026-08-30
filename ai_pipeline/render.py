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

from shared.captions import blank_png, caption_box, pad_to_box, render_caption
from shared.ffmpeg import exe
from shared.frames import caption_sequence

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
    box_rgba: tuple[int, int, int, int] = (10, 12, 18, 200)
    highlight_rgb: tuple[int, int, int] = (242, 200, 121)
    y_ratio: float = 0.64


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


# ── الكابشن: PNG لكل مقطع، وتسلسل مفهرس بالإطار ──────────────────────
def rasterise_captions(
    timeline: Timeline, segments: SegmentsContract,
    typo: TypographyContract, output: Output, style: CaptionStyle,
    workdir: str | Path,
) -> str:
    """بيرجّع نمط `…/%06d.png` جاهز لـ`-framerate FPS -start_number 0`.

    **القاعدة بتيجي من `shared`، والكتابة بس هون.** خريطة إطار->صورة من
    `shared.frames.caption_sequence`، والتوحيد على صندوق واحد من
    `shared.captions.caption_box`/`pad_to_box`. اللي انكتب هون حلقة
    الوصلات الرمزية، وهي **آلية مش سياسة**.

    وليش انكتبت بدل ما تنستدعى: `autoreel.render.materialise_captions`
    بتعمل نفس الحلقة، بس `shared/` ما بتعيد تصديرها و`ai_pipeline`
    ممنوعة تستورد `autoreel` مباشرة. وبعد هالcommit صارت **مستدعاة من
    النظامين فعلًا** — يعني انطبقت عليها قاعدة الترقية لـ`shared/`.
    ترقيتها commit مستقل، لأن `shared/` مقفولة بهاد.
    """
    work = Path(workdir)
    png_dir, seq_dir, box_dir = work / "png", work / "seq", work / "box"
    for d in (png_dir, seq_dir, box_dir):
        d.mkdir(parents=True, exist_ok=True)

    by_id = {s.segment_id: s for s in segments.segments}
    frames: list[tuple[str, int, int]] = []
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
        cfg = {
            "font": str(style.font), "size": ov.font_size,
            "color": list(bytes.fromhex(ov.text_color[1:])),
            "highlight": list(style.highlight_rgb),
            "box": list(style.box_rgba), "y_ratio": style.y_ratio,
        }
        p = png_dir / f"{sp.segment_id:04d}.png"
        render_caption(seg.text_arabic, cfg, output.width).save(p)
        frames.append((str(p), sp.f_start, sp.f_end))

    # **كل صور التسلسل بنفس المقاس بالضبط.** مُدخل الصور بياخد أبعاد
    # التيار من أول ملف، وفرق بكسل واحد بيقطع المخرَج بصمت: ٤٠٧×٢٠٨
    # و٤٠٨×٢٠٨ أعطت ٧٣ إطار من ١٤٤ (مقيسة بهالمستودع).
    seq = caption_sequence(frames, timeline.total_frames)
    distinct = sorted({p for p in seq if p})
    box = caption_box(distinct) if distinct else (2, 2)
    padded = {p: pad_to_box(p, str(box_dir / f"{i:05d}.png"), box)
              for i, p in enumerate(distinct)}
    empty = (blank_png(str(box_dir / "blank.png"), box)
             if any(p is None for p in seq) else None)

    use_symlink = True
    for n, png in enumerate(seq):
        dst = seq_dir / f"{n:06d}.png"
        target = os.path.abspath(padded[png] if png is not None else empty)
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
    style: CaptionStyle, encode: Encode = Encode(), dry_run: bool = False,
) -> list[str]:
    """بيرسم ويرجّع الأمر اللي انشغّل (أو اللي **كان** بينشغّل).

    `dry_run` بيوقف قبل ffmpeg وبعد رسم الكابشن: التسلسل بينكتب فعلًا،
    فالمطبوع هو الأمر الحقيقي مش تقريبًا إله.
    """
    pattern = rasterise_captions(timeline, segments, typo, output, style,
                                 workdir)
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
