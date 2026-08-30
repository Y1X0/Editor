"""نقطة التشغيل — أمر واحد، من الصوت للفيديو.

هالملف بيسأل التلات أسئلة اللي CLI بتوجد لتجاوبهن:

  ١· بيشتغل؟          أمر واحد -> ملف بيمرق حارس المخرَج
  ٢· بيوقف صح؟        كل مدخل مكسور -> رمز مرحلة، بلا ملف نصّي
  ٣· بيوقف عند حدّه؟  ولا شبكة، ولا SDK، ولا قارئ مدة تاني

والسؤال التالت هو الأهم: CLI هي أول مكان بيلمس كل الطبقات مع بعض،
فهي كمان أول مكان بيقدر يخترق حدًّا بالغلط.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from ai_pipeline.cli import build_parser, main

ROOT = Path(__file__).resolve().parents[2]
FONT = ROOT / "fonts" / "Amiri-Bold.ttf"

SCRIPT = "الحمد لله رب العالمين الرحمن الرحيم"
SRT = """\
1
00:00:00,500 --> 00:00:02,500
الحمد لله رب

2
00:00:03,000 --> 00:00:05,000
العالمين الرحمن الرحيم
"""

RECORDED = {
    "script_v1": {"segments": [
        {"segment_id": 1, "word_start": 0, "word_end": 3,
         "visual_mood_prompt": "still dark sky"},
        {"segment_id": 2, "word_start": 3, "word_end": 6,
         "visual_mood_prompt": "warm dawn light"}]},
    "visual_v1": {"intents": [
        {"segment_id": 1, "query": "dark blue night calm",
         "must_include": ["dark"], "must_avoid": [], "shot_type": "abstract",
         "palette": "deep_blue", "motion": "zoom_in"},
        {"segment_id": 2, "query": "warm gold dawn glow",
         "must_include": ["gold"], "must_avoid": [], "shot_type": "abstract",
         "palette": "warm_gold", "motion": "none"}]},
    "typography_v1": {"segments": [
        {"segment_id": 1, "animation": "fade", "font_role": "body",
         "size_step": 0, "color_role": "primary"},
        {"segment_id": 2, "animation": "fade_in_up", "font_role": "body",
         "size_step": 0, "color_role": "accent"}]},
}


@pytest.fixture
def project(tmp_path):
    """مشروع كامل على القرص: صوت · نص · SRT · كتالوج · استجابات."""
    import hashlib
    from shared.ffmpeg import exe

    (tmp_path / "script.txt").write_text(SCRIPT + "\n", encoding="utf-8")
    (tmp_path / "subs.srt").write_text(SRT, encoding="utf-8")

    subprocess.run([exe(), "-v", "error", "-f", "lavfi",
                    "-i", "sine=f=200:r=48000", "-af", "atrim=end_sample=288000",
                    "-ac", "1", "-c:a", "pcm_s16le", "-y",
                    str(tmp_path / "voice.wav")], check=True)          # 6.0s

    entries = []
    specs = [("dark.mp4", "px_dark", "gradients=s=320x240:c0=0x050A18:c1=0x12244A:r=10",
              ("dark", "night", "calm"), "deep_blue"),
             ("gold.mp4", "px_gold", "gradients=s=320x240:c0=0x2A1A05:c1=0xD9A441:r=10",
              ("gold", "warm", "dawn"), "warm_gold")]
    for name, ref, src, kw, pal in specs:
        p = tmp_path / name
        subprocess.run([exe(), "-v", "error", "-f", "lavfi", "-i", src,
                        "-frames:v", "80", "-r", "10", "-pix_fmt", "yuv420p",
                        "-c:v", "libx264", "-preset", "ultrafast", "-an",
                        "-y", str(p)], check=True)                      # 8.0s
        entries.append({
            "provider": "lavfi", "provider_ref": ref, "path": name,
            "license": "CC0", "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "probe": {"width": 320, "height": 240, "fps": 10.0, "duration": 8.0},
            "keywords": list(kw), "shot_type": "abstract", "palette": pal,
            "attribution": None, "source_type": "generated"})
    (tmp_path / "catalog.json").write_text(
        json.dumps({"entries": entries}), encoding="utf-8")

    fix = tmp_path / "fixtures"
    for key, payload in RECORDED.items():
        d = fix / key
        d.mkdir(parents=True)
        (d / "ok.json").write_text(json.dumps(
            {"text": json.dumps(payload, ensure_ascii=False),
             "stop_reason": "end_turn", "model": "recorded-fixture"}),
            encoding="utf-8")
    return tmp_path


def argv(project, out, *extra):
    return ["--audio", str(project / "voice.wav"),
            "--script", str(project / "script.txt"),
            "--srt", str(project / "subs.srt"),
            "--catalog", str(project / "catalog.json"),
            "--recorded", str(project / "fixtures"),
            "--font", str(FONT),
            "--width", "216", "--height", "384", "--fps", "10",
            "--project-id", "cli-test", "-o", str(out), *extra]


# ══════════════════ ١· بيشتغل ═══════════════════════════════════════
@pytest.mark.ffmpeg
def test_one_command_turns_audio_and_text_into_a_video(project, capsys):
    """السلسلة كاملة، وحارس المخرَج بيقول إن الملف طابق الخطة."""
    from ai_pipeline.io import contracts as io
    from ai_pipeline.models.project import Project
    from ai_pipeline.models.timeline import Timeline
    from ai_pipeline.qa.output import verify_output

    out = project / "out.mp4"
    assert main(argv(project, out)) == 0
    assert out.is_file() and out.stat().st_size > 0
    assert capsys.readouterr().out.strip() == str(out)   # stdout = المسار وبس

    work = Path(str(out) + ".work")
    tl = io.load(io.contract_path(work, "timeline"), Timeline)
    pr = verify_output(out, tl, io.load(
        io.contract_path(work, "project"), Project).output)
    assert pr.frames == tl.total_frames == 60             # 6.0s × 10fps


@pytest.mark.ffmpeg
def test_all_six_contracts_land_on_disk(project):
    out = project / "out.mp4"
    assert main(argv(project, out)) == 0
    c = Path(str(out) + ".work") / "contracts"
    assert sorted(p.stem for p in c.glob("*.json")) == [
        "alignment", "assets", "project", "segments", "timeline", "typography"]


@pytest.mark.ffmpeg
def test_provenance_records_the_run_not_a_guess(project):
    """`provenance` بيجي من التشغيلة نفسها — بصمة المدخلات ونسخة ffmpeg
    والنموذج اللي ردّ فعلًا، مش قيمًا مكتوبة سلفًا."""
    import hashlib
    from ai_pipeline.io import contracts as io
    from ai_pipeline.models.project import Project

    out = project / "out.mp4"
    main(argv(project, out))
    pj = io.load(io.contract_path(Path(str(out) + ".work"), "project"), Project)
    assert pj.source.script_sha256 == hashlib.sha256(
        (project / "script.txt").read_bytes()).hexdigest()
    assert pj.source.audio_sha256 == hashlib.sha256(
        (project / "voice.wav").read_bytes()).hexdigest()
    assert pj.provenance.llm_model == "recorded-fixture"
    assert pj.provenance.llm_prompt_sha256 is not None
    assert pj.provenance.ffmpeg_version


@pytest.mark.ffmpeg
def test_the_agent_log_records_every_call(project):
    out = project / "out.mp4"
    main(argv(project, out))
    log = (Path(str(out) + ".work") / "agent_runs.jsonl").read_text()
    rows = [json.loads(l) for l in log.splitlines()]
    assert [r["agent"] for r in rows] == ["script", "visual", "typography"]
    assert all(r["validation"] == "ok" and r["attempt"] == 1 for r in rows)
    # السجلّ **بيانات وصفية بس** — ولا نصّ مصدري ولا محتوى استجابة
    assert "الحمد" not in log


@pytest.mark.ffmpeg
def test_dry_run_prints_the_command_and_encodes_nothing(project, capsys):
    out = project / "out.mp4"
    assert main(argv(project, out, "--dry-run")) == 0
    assert not out.exists()
    printed = capsys.readouterr().out
    assert "-filter_complex" in printed and str(out) in printed


# ══════════════════ ٢· بيوقف صح ═════════════════════════════════════
@pytest.mark.parametrize("break_it,code", [
    (lambda p: (p / "subs.srt").write_text(
        SRT.replace("العالمين", "العالمون"), encoding="utf-8"),
     "ALIGNMENT_ERROR"),
    (lambda p: (p / "script.txt").write_text("", encoding="utf-8"),
     "CONTRACT_ERROR"),
    (lambda p: (p / "voice.wav").unlink(),
     "ASSET_ERROR"),
    (lambda p: (p / "catalog.json").write_text("{ nope", encoding="utf-8"),
     "CONTRACT_ERROR"),
    (lambda p: (p / "dark.mp4").write_bytes(b"tampered"),
     "ASSET_ERROR"),
])
@pytest.mark.ffmpeg
def test_a_broken_input_stops_with_its_stage_code(project, capsys, break_it,
                                                  code):
    """**الرمز جزء من العقد، والرسالة لأ.** وولا ملف مخرَج بأي حالة.

    آخر حالة بالذات: الملف تبدّل بعد ما انتسجّل بالكتالوج، فبصمته ما
    عادت تطابق — والـResolver بيرفضه. بلا هالحاجز، فيديو بينبنى من
    محتوى ما حدا تحقّق منه.
    """
    out = project / "out.mp4"
    break_it(project)
    assert main(argv(project, out)) == 1
    assert code in capsys.readouterr().err
    assert not out.exists()


@pytest.mark.ffmpeg
def test_a_missing_recorded_fixture_fails_closed(project, capsys):
    """المزوّد ما بيخترع استجابة، والـCLI ما بتهبط لمقسِّم قاعدي."""
    (project / "fixtures" / "visual_v1" / "ok.json").unlink()
    out = project / "out.mp4"
    assert main(argv(project, out)) == 1
    assert "PROVIDER_ERROR" in capsys.readouterr().err
    assert not out.exists()


# ══════════════════ ٣· بيوقف عند حدّه ═══════════════════════════════
@pytest.mark.ffmpeg
def test_the_run_never_touches_the_network_or_the_sdk(project, monkeypatch):
    """ولا `anthropic`، ولا مفتاح، ولا socket — على **التشغيلة الكاملة**.

    مش على المزوّد لحاله: CLI هي أول مكان بيجمع كل الطبقات، فهي أول
    مكان بيقدر يفتح قناة جانبية بالغلط.
    """
    import socket

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(socket.socket, "connect", lambda *a, **k: pytest.fail(
        "التشغيلة فتحت اتصال شبكة"))
    real = __import__

    def guard(name, *a, **k):
        if name.split(".")[0] == "anthropic":
            pytest.fail("انستورد anthropic أثناء التشغيل")
        return real(name, *a, **k)

    monkeypatch.setattr("builtins.__import__", guard)
    assert main(argv(project, project / "out.mp4")) == 0
    assert "anthropic" not in sys.modules


@pytest.mark.ffmpeg
def test_the_duration_is_read_exactly_once_and_by_probe_audio(project,
                                                              monkeypatch):
    """**قارئ واحد للمدة بكل التشغيلة، وهو `probe_audio`.**

    هاد اللي Commit 11 حطّ عليه حارسًا ثابتًا وCommit 12 منع تكراره
    بالراسم؛ وهون بينقاس على التشغيلة الحقيقية بدل ما ينستنتج.
    """
    import ai_pipeline.cli as C
    calls = []
    real = C.probe_audio
    monkeypatch.setattr(C, "probe_audio",
                        lambda p: (calls.append(p), real(p))[1])
    assert main(argv(project, project / "out.mp4")) == 0
    assert len(calls) == 1, f"المدة انقرات {len(calls)} مرات"
    assert Path(calls[0]).name == "voice.wav"


def test_the_cli_offers_no_live_provider_flag():
    """المزوّد الوحيد اليوم مسجَّل. `--anthropic` ما إله وجود بعد.

    الحارس بيفشل لما ينضاف المزوّد الحقيقي — وهاد المقصود: إضافته
    قرار بcommit مستقل، مش انزلاقًا يمرق مع تغيير تاني.
    """
    flags = {a for act in build_parser()._actions for a in act.option_strings}
    assert "--recorded" in flags
    assert not {"--anthropic", "--api-key", "--model"} & flags


# ══════════════ ٤· كل مدقّق بالـCLI لازم يكون قابلًا للفشل ═══════════
# الطفرة اللي بتشيل النداء لازم تفشّل فحصًا هون. مدقّق ما في مدخل
# بيوصله هو **نيّة حماية**، مش حماية — والفرق بينهن ما بيبيّن إلا
# بطفرة. تلاتة انشالوا من الـCLI لهالسبب بالضبط.

@pytest.mark.ffmpeg
def test_an_srt_that_outruns_the_audio_is_rejected(project, capsys):
    """`check_audio_matches_alignment` — الصوت ٦.٠s والكلام لحد ٧.٠s.

    بلا الحاجز: `quantize` بتقصّ آخر مقطع على `total_frames` بصمت،
    فالجملة الأخيرة بتنقطع بنصّها والمخرَج بيبيّن سليمًا.
    """
    (project / "subs.srt").write_text(
        SRT.replace("00:00:05,000", "00:00:07,000"), encoding="utf-8")
    assert main(argv(project, project / "out.mp4")) == 1
    err = capsys.readouterr().err
    assert "ALIGNMENT_ERROR" in err and "بتتجاوز الصوت" in err


@pytest.mark.ffmpeg
def test_a_font_that_cannot_draw_the_text_is_rejected(project, capsys):
    """`check_font_can_render` — **قبل** الترميز، مش بعده.

    مقيس: `Tajawal-Bold` ما فيها `U+0671` (ألف الوصل) ولا `U+06DA`،
    فبتطلّعهن دوائر منقّطة. بلا الحاجز بينكتشف بالعين بعد دقايق ترميز،
    وبمخرَج بيبيّن ناجحًا.
    """
    text = "ٱلحمد لله رب ٱلعالمين الرحمن الرحيم"       # فيها U+0671
    (project / "script.txt").write_text(text + "\n", encoding="utf-8")
    (project / "subs.srt").write_text(
        SRT.replace("الحمد لله رب", "ٱلحمد لله رب")
           .replace("العالمين الرحمن", "ٱلعالمين الرحمن"), encoding="utf-8")
    out = project / "out.mp4"
    # **خط الأساس أولًا**: نفس النصّ مع Amiri بينجح — فالفشل تحت عن
    # الخط، مش عن النصّ ولا عن باقي المسار.
    assert main(argv(project, out)) == 0
    out.unlink()
    capsys.readouterr()

    args = argv(project, out)
    args[args.index("--font") + 1] = str(ROOT / "fonts" / "Tajawal-Bold.ttf")
    assert main(args) == 1
    assert "0671" in capsys.readouterr().err.lower().replace("u+", "")
    assert not out.exists()


@pytest.mark.ffmpeg
def test_typography_for_an_unknown_segment_is_rejected(project, capsys):
    """`check_typography` — الوكيل سمّى مقطعًا مش موجودًا.

    `expand_typography_proposal` ما بتشوف `segments`: بتتحقّق من الدور
    والحجم واللون وبس. فالمعرّف المخترَع بيمرق منها، وهاد الحاجز الوحيد
    اللي بيمسكه.
    """
    # المقطعان الحقيقيان موجودان **زائد** واحد مخترَع: هيك بيشتغل فرع
    # «typography لمقاطع مش موجودة» بدل فرع «مقاطع بلا typography».
    bad = {"segments": [
        {"segment_id": i, "animation": "fade", "font_role": "body",
         "size_step": 0, "color_role": "primary"} for i in (1, 2, 9)]}
    (project / "fixtures" / "typography_v1" / "ok.json").write_text(
        json.dumps({"text": json.dumps(bad), "stop_reason": "end_turn",
                    "model": "recorded-fixture"}), encoding="utf-8")
    assert main(argv(project, project / "out.mp4")) == 1
    err = capsys.readouterr().err
    assert "CONTRACT_ERROR" in err and "مش موجودة: [9]" in err


@pytest.mark.ffmpeg
def test_the_cli_fails_when_the_output_guard_rejects_the_file(project, capsys,
                                                             monkeypatch):
    """`verify_output` موصول بمسار الفشل، مش منادى وبيتجاهَل ناتجه.

    `exit code 0` من ffmpeg مش إثباتًا — مقيس بهالمستودع: فرق بكسل
    واحد بتسلسل الصور أعطى ٧٣ إطار من ١٤٤ وffmpeg خرج بصفر.
    """
    import ai_pipeline.cli as C
    from ai_pipeline.errors import QaError

    def reject(*a, **k):
        raise QaError("المخرَج ما طابق الخطة (مُصطنَع)")

    monkeypatch.setattr(C, "verify_output", reject)
    assert main(argv(project, project / "out.mp4")) == 1
    assert "QA_ERROR" in capsys.readouterr().err


def test_the_cli_refuses_an_unverified_ffmpeg(project, capsys, monkeypatch):
    """`check_ffmpeg` موصول: تحت الأدنى بيرمي قبل أي شغل."""
    import ai_pipeline.cli as C
    monkeypatch.setattr(C, "check_ffmpeg", lambda: (_ for _ in ()).throw(
        RuntimeError("ffmpeg 5.0 أقدم من الأدنى المدعوم")))
    assert main(argv(project, project / "out.mp4")) == 1
    assert "FFMPEG" in capsys.readouterr().err


# ══════════════════ طبقة الصوت ══════════════════════════════════════
#
# **تلات فحوص انولدوا من طفرات مرقت.** الطقم كان أخضر وهو ما بيغطّي
# ولا وحدة منهن — نفس درس «افحص الحارس بحالة سيّئة معروفة».
@pytest.mark.ffmpeg
def test_the_cli_reads_the_channel_count_and_compensates(project, capsys):
    """`voice.wav` بالـfixture **مونو** (`-ac 1`)، فالتعويض لازم يبيّن.

    الطفرة اللي كشفت الفراغ: تكميم `channels = 2` بالـCLI. مرقت،
    لأن ولا فحص كان بيوصل لعدد القنوات الحقيقي — والنتيجة كلام
    ٣dB تحت المعايرة بلا أي عرَض ظاهر.
    """
    from ai_pipeline.render import SPEECH_UPMIX_GAIN
    out = project / "o.mp4"
    assert main(argv(project, out, "--sfx", "--dry-run")) == 0
    cmd = capsys.readouterr().out
    assert f"volume={SPEECH_UPMIX_GAIN:.6f}" in cmd
    assert "1ch" not in cmd                       # السطر التقريري على stderr


@pytest.mark.ffmpeg
def test_a_stereo_voice_is_not_compensated(project, capsys):
    """نفس المشروع بصوت ستيريو: **ولا تعويض.** بيمسك الطفرة المعاكسة
    (تعويض بلا شرط) على مستوى الـCLI مش الراسم بس."""
    from shared.ffmpeg import exe
    from ai_pipeline.render import SPEECH_UPMIX_GAIN
    st = project / "stereo.wav"
    subprocess.run([exe(), "-v", "error", "-i", str(project / "voice.wav"),
                    "-af", "pan=stereo|c0=c0|c1=c0", "-c:a", "pcm_s16le",
                    "-y", str(st)], check=True)
    out = project / "o.mp4"
    a = argv(project, out, "--sfx", "--dry-run")
    a[a.index("--audio") + 1] = str(st)
    assert main(a) == 0
    assert f"volume={SPEECH_UPMIX_GAIN:.6f}" not in capsys.readouterr().out


@pytest.mark.ffmpeg
def test_a_bad_music_gain_fails_early_and_classified(project, capsys):
    """الحارس لازم يضرب **قبل** أي وكيل وأي ترميز، وبنوع خطأ مصنَّف.

    الطفرة اللي مرقت: شيل النداء المبكّر. الحارس الحقيقي بيضل
    بـ`autoreel.graph` فالخطأ بيطلع — بس كـ`ValueError` عارية بعد
    ما كل الوكلاء اشتغلوا. الفرق بيبيّن بالسطر التقريري: لو الحارس
    اشتغل بوقته، ولا مرحلة بعد «ffmpeg» بتنطبع.
    """
    out = project / "o.mp4"
    assert main(argv(project, out, "--music", str(project / "voice.wav"),
                     "--music-gain", "0.30")) == 1
    err = capsys.readouterr().err
    assert "CONTRACT_ERROR" in err and "--music-gain" in err
    assert "كلمة · صوت" not in err, "الحارس اشتغل متأخّرًا — بعد قراءة المدخلات"
