"""نقطة التشغيل — أمر واحد بيمشّي السلسلة كاملة.

```bash
python -m ai_pipeline.cli \
    --audio voice.wav --script script.txt --srt subs.srt \
    --catalog catalog.json --recorded fixtures/ -o out.mp4
```

    صوت + SRT + نص
        ↓  probe_audio          ← **هون بتنقاس المدة، وهون بس**
        ↓  alignment_from_srt
        ↓  Script Agent  ──► segments.json
        ↓  visual window ──► المدة المطلوبة لكل مقطع
        ↓  Visual Agent + Resolver ──► assets.json
        ↓  Typography Agent ──► typography.json
        ↓  quantize ──► timeline.json
        ↓  render ──► ffmpeg ──► out.mp4
        ↓  qa.verify_output

**هالملف هو مالك قياس المدة.** `render.py` ما بيقيس، و`quantize` بتاخدها
كوسيط — فما في إلا قارئ واحد بكل المسار، وعليه حارس بـ
`test_audio_duration.py`.

**وهو كمان مكان المدقّقات.** سبع دوال بـ`validation/` انكتبت بPhase 2
وضلّت بلا مستدعي لحدّ هون. مدقّق بلا مستدعي مش حماية، هو نيّة حماية.

**ولا Anthropic بهالملف.** المزوّد الوحيد اليوم `RecordedClient`:
استجابات مسجَّلة، بلا شبكة وبلا مفتاح. المزوّد الحقيقي بيجي بcommit
منفصل خلف نفس الواجهة — والسلسلة كلها ما بتتغيّر.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from shared.audio import music_chain
from shared.ffmpeg import exe
from shared.probe import check_ffmpeg, ffmpeg_version

from . import render as R
from .agents import script as script_agent
from .agents import typography as typo_agent
from .agents import visual as visual_agent
from .agents.expand import ThemeView
from .agents.providers.recorded import RecordedClient
from .agents.resolver import load_catalog, resolve
from .agents.runner import AgentHarness, jsonl_sink
from .errors import ContractError, NurError
from .io import contracts as io
from .models.project import Output, Project, Provenance, Source
from .qa.output import verify_output
from .source import tokenize
from .srt import alignment_from_srt
from .timeline.quantize import quantize
from .validation.font import check_font_can_render
from .validation.inputs import (
    check_audio_matches_alignment, check_script, probe_audio,
)
from .validation.semantic import check_typography
from .window import required_seconds

TOOL_VERSION = "ai_pipeline/0.1"

ROOT = Path(__file__).resolve().parent.parent

#: theme واحد مدمَج. **مؤقّت بقصد** — `themes/*.json` مرحلة لاحقة،
#: وتعريف صيغة ملف theme الآن بيثبّت واجهة قبل ما يكون إلها تاني
#: مستهلك. الخط بينداهس بـ`--font` لأنه القرار الوحيد اللي بيتغيّر
#: عمليًا بين نصّ وآخر (Amiri للنص العام، AmiriQuran للقرآني).
THEMES = {
    "nur-dark": dict(
        font_role="body", base_font_size=66, size_step_px=3,
        # **تباين قبل ذوق.** الأدوار التلاتة كلها فاتحة بقصد: خلفيات
        # الـtheme داكنة، ولون قريب منها (ذهبي على ذهبي) بيضيع مهما
        # كانت الهالة. الذهبي محجوز لإبراز الكلمة المنطوقة وحده.
        color_hex={"primary": "#FFFFFF", "muted": "#EDEDED",
                   "accent": "#FFF4DC"},
        max_lines=2, fit="cover"),
}


@dataclass(frozen=True)
class Stage:
    """سطر تقدّم واحد. الطباعة على stderr عشان stdout يضل للنتيجة."""

    quiet: bool = False

    def __call__(self, msg: str) -> None:
        if not self.quiet:
            print(f"  · {msg}", file=sys.stderr, flush=True)


#: تخطيطات القنوات اللي بيسمّيها ffmpeg، ورقمها.
_LAYOUTS = {"mono": 1, "stereo": 2, "5.1": 6, "5.1(side)": 6, "7.1": 8}
_ACHAN = re.compile(r"Audio: [^\n]*?, \d+ Hz, ([^,]+),")


def speech_channels(path: str | Path) -> int:
    """عدد قنوات ملف الكلام. **حقيقة عن المصدر، بتنقرا هون مرة.**

    ليش هون ومش بـ`probe_audio`: `validation/` شجرة مجمَّدة، وهاي
    قراءة جديدة انلزمت لطبقة الصوت لحالها. ونفس قرار `audio_duration`:
    الـCLI بتقرا الحقائق عن المُدخَل، والراسم بياخدها كوسيط.

    والرقم بيقرّر تعويض الرفع الضمني لستيريو — شوف
    `render.SPEECH_UPMIX_GAIN`. **بلاه بيصير الكلام ٣dB تحت المعايرة
    بصمت، وولا تحذير من ffmpeg.**

    بيرجّع ٢ لأي تخطيط مش معروف: التعويض بينطبّق على المونو بس،
    فالمجهول بياخد المسار اللي ما بيلمس شي.
    """
    r = subprocess.run([exe(), "-hide_banner", "-i", str(path)],
                       capture_output=True, text=True)
    m = _ACHAN.search(r.stderr)
    return _LAYOUTS.get(m.group(1).strip(), 2) if m else 2


def sha256_of(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m ai_pipeline.cli",
        description="نص + صوت -> فيديو عمودي، بأمر واحد.")
    g = ap.add_argument_group("المدخلات")
    g.add_argument("--audio", required=True, type=Path,
                   help="ملف الصوت. **المدة بتنقاس منه هون، ومن هون بس.**")
    g.add_argument("--script", required=True, type=Path,
                   help="النص المصدر — ولا حرف منه بيتغيّر (§19)")
    g.add_argument("--srt", required=True, type=Path,
                   help="توقيت الجمل. كلماته لازم تطابق النص بالضبط")
    g.add_argument("--catalog", required=True, type=Path,
                   help="كتالوج الأصول الموثوق — الـResolver بيختار منه")

    g = ap.add_argument_group("المزوّد")
    g.add_argument("--recorded", required=True, type=Path,
                   help="مجلّد استجابات مسجَّلة. **المزوّد الوحيد اليوم** — "
                        "بلا شبكة وبلا مفتاح")
    g.add_argument("--case", default="ok", help="اسم الحالة المسجَّلة")

    g = ap.add_argument_group("المخرَج")
    g.add_argument("-o", "--out", required=True, type=Path)
    g.add_argument("--workdir", type=Path,
                   help="العقود والكابشن والسجلّ. الافتراضي `<out>.work`")
    g.add_argument("--width", type=int, default=1080)
    g.add_argument("--height", type=int, default=1920)
    g.add_argument("--fps", type=int, default=30)
    g.add_argument("--sample-rate", type=int, default=48000)

    g = ap.add_argument_group("الأسلوب")
    g.add_argument("--theme", default="nur-dark", choices=sorted(THEMES))
    g.add_argument("--font", type=Path,
                   default=ROOT / "fonts" / "Tajawal-ExtraBold.ttf")
    g.add_argument("--y-ratio", type=float, default=0.70)
    g.add_argument("--project-id", default="untitled")

    g = ap.add_argument_group("الصوت")
    g.add_argument("--sfx", action="store_true",
                   help="مؤثرات عند البداية والقطعات وظهور الكابشن. "
                        "**مطفية افتراضيًا** — تشغيلها بيضرب الكلام بـ0.70")
    g.add_argument("--music", type=Path,
                   help="موسيقى خلفية. بتنلفّ وبتنقصّ لطول الشريط")
    g.add_argument("--music-gain", type=float, default=0.12)

    ap.add_argument("--dry-run", action="store_true",
                    help="بيبني كل شي وبيطبع أمر ffmpeg بلا ترميز")
    ap.add_argument("-q", "--quiet", action="store_true")
    return ap


def run(args: argparse.Namespace) -> int:
    say = Stage(args.quiet)
    work = args.workdir or Path(str(args.out) + ".work")
    work.mkdir(parents=True, exist_ok=True)

    # ── ٠· البيئة والأعلام ──────────────────────────────────────────
    check_ffmpeg()                      # تحت الأدنى بيرمي، وبينهما بيحذّر
    # **حارس الهامش بينشتغل هون، قبل أي وكيل وأي ترميز.** واللي
    # بينادى هو الحارس **نفسه** بـ`autoreel.graph`، مش نسخة عنه:
    # حسبة تانية للهامش بتفترق بصمت عن الأصلية.
    if args.music is not None:
        try:
            music_chain(0, gain=args.music_gain)
        except ValueError as e:
            raise ContractError(f"--music-gain: {e}") from e
    ffv = ".".join(map(str, ffmpeg_version()))
    say(f"ffmpeg {ffv}")

    # ── ١· المدخلات ──────────────────────────────────────────────────
    script_text = check_script(args.script)
    tokens = tokenize(script_text)
    audio_duration, codec, in_rate = probe_audio(args.audio)
    channels = speech_channels(args.audio)
    say(f"{len(tokens)} كلمة · صوت {audio_duration}s ({codec} @ {in_rate}Hz"
        f" · {channels}ch)")

    output = Output(width=args.width, height=args.height, fps=args.fps,
                    sample_rate=args.sample_rate)

    # ── ٢· المحاذاة — السلطة الزمنية ─────────────────────────────────
    alignment = alignment_from_srt(args.srt, tokens)
    # **`check_alignment_matches_source` مش منداة هون بقصد.**
    # `alignment_from_srt` بتبنيها من كلمات تحقّقت مقابل المصدر أصلًا
    # (عدد ونصّ)، فالنداء هون **ما بيقدر ينفشل** — وحارس ما بينقدر
    # ينفشل بيوهم بأمان مش موجودًا. مقيس: شيلها من هون وما بيفشل ولا
    # فحص. مكانها الصح مصدر محاذاة تاني (Whisper)، وقتها بينندى بقصد.
    check_audio_matches_alignment(audio_duration, alignment)
    say(f"محاذاة: {len(alignment.words)} كلمة، مطابقة للمصدر وداخل الصوت")

    # ── ٣· الوكلاء ───────────────────────────────────────────────────
    theme = ThemeView(theme_id=args.theme, **THEMES[args.theme])
    client = RecordedClient(args.recorded, args.case)
    harness = AgentHarness(client, sink=jsonl_sink(work / "agent_runs.jsonl"))

    segments = script_agent.run(client, script_text, tokens, harness=harness)
    # ونفس السبب لـ`check_alignment_covers`: `expand_segments_proposal`
    # بترفض أي مدى خارج عدد الكلمات، و`len(alignment) == len(tokens)`
    # مضمونة فوق — فالشرطان واحد.
    say(f"Script: {len(segments.segments)} مقاطع")

    # الخط بينفحص **على النص الفعلي**، قبل أي ترميز: خط ما بيرسم علامة
    # وقف بيطلّع دائرة منقّطة، وهاد بينكتشف بالعين بعد دقايق ترميز.
    check_font_can_render(args.font, [s.text_arabic for s in segments.segments])

    required = required_seconds(output, segments, alignment, audio_duration)
    intent = visual_agent.run(client, segments, harness=harness)
    catalog, catalog_root = load_catalog(args.catalog)
    # `resolve` بتتحقّق من الوجود والبصمة والرخصة لكل أصل، و
    # `expand_asset_intents` بتفرض تطابق المعرّفات — فـ`check_assets`
    # كمان ما بتقدر تنفشل بعدهن. تلاتة انشالوا لنفس السبب، والمقياس
    # واحد: طفرة بتشيل النداء وما بتفشّل ولا فحص.
    assets = resolve(intent, required, catalog, catalog_root, theme)
    say("Visual + Resolver: " + " · ".join(
        f"#{a.segment_id}->{a.provider_ref}" for a in assets.assets))

    typo = typo_agent.run(client, segments, theme, harness=harness)
    check_typography(typo, segments, theme.theme_id)
    say("Typography: " + " · ".join(
        f"#{s.segment_id} {s.animation}" for s in typo.segments))

    # ── ٤· الحدّ: ثواني ──► إطارات ───────────────────────────────────
    timeline = quantize(output, segments, alignment, assets, audio_duration)
    say(f"Timeline: {timeline.total_frames} إطار · "
        f"{timeline.total_samples} عيّنة")

    # ── ٥· العقود على القرص ─────────────────────────────────────────
    llm_model = next((r["model"] for r in harness.runs if r["model"]), None)
    prompt_sha = next((r["prompt_sha256"] for r in harness.runs
                       if r["agent"] == "script"), None)
    project = Project(
        project_id=args.project_id,
        source=Source(script_sha256=sha256_of(args.script),
                      audio_sha256=sha256_of(args.audio)),
        output=output, theme=theme.theme_id,
        provenance=Provenance(tool_version=TOOL_VERSION, ffmpeg_version=ffv,
                              whisper_model=None, llm_model=llm_model,
                              llm_prompt_sha256=prompt_sha))
    for name, obj in (("project", project), ("alignment", alignment),
                      ("segments", segments), ("assets", assets),
                      ("typography", typo), ("timeline", timeline)):
        io.save(io.contract_path(work, name), obj)
    say(f"عقود: {work / 'contracts'}")

    # ── ٦· الرسم ─────────────────────────────────────────────────────
    style = R.CaptionStyle(font=args.font, y_ratio=args.y_ratio)
    audio_cfg = R.Audio(sfx=args.sfx, music=args.music,
                        music_gain=args.music_gain,
                        speech_channels=channels)
    if args.sfx or args.music:
        say("صوت: " + " · ".join(
            x for x in ("مؤثرات" if args.sfx else "",
                        f"موسيقى @{args.music_gain}" if args.music else "") if x))
    cmd = R.render(timeline, segments, assets, typo, output,
                   audio=args.audio, out_path=args.out, workdir=work,
                   style=style, alignment=alignment, audio_cfg=audio_cfg,
                   dry_run=args.dry_run)
    if args.dry_run:
        print(" ".join(cmd))            # stdout — للأنبوب
        say("dry-run: ولا ترميز")
        return 0

    # ── ٧· الحارس الأخير: على الملف، مش على الخطة ───────────────────
    pr = verify_output(args.out, timeline, output)
    say(f"QA ✓ {pr.frames} إطار · {pr.width}x{pr.height} · "
        f"{pr.audio_samples} عيّنة")
    print(args.out)                     # stdout — المسار وبس
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except NurError as e:
        # **رمز المرحلة جزء من العقد مع المستخدم**، والرسالة ممكن
        # تتغيّر. ولا traceback: الخطأ مصنَّف أصلًا، والأثر بيخبّي السطر
        # اللي بيقول شو يعمل.
        print(f"\n{e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        # `shared.probe` بترمي `RuntimeError` (نوع المحرر)، فما بينلفّ
        # بـ`NurError` هون: لفّه بيخفي مصدره.
        print(f"\n[FFMPEG] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":              # pragma: no cover
    raise SystemExit(main())
