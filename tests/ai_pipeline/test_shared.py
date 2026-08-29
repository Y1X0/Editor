"""حرّاس الحدّ بين الأنظمة.

القاعدة: `shared/` **تفويض**، مش نسخ. وأي منطق بينتنسخ هون بيصير
تعريفًا تانيًا بينفترق بصمت — وهاد سجلّ موثَّق بهالمستودع
(`motion.pan_px` انفصلت عن قارئها و١٩٠ فحصًا ما مسكوها).
"""
import ast
import importlib
import pathlib

import pytest

import shared.captions
import shared.frames
import shared.probe
from autoreel import captions as A_CAP
from autoreel import cuts as A_CUTS
from autoreel import graph as A_GRAPH
from autoreel import render as A_REN
from autoreel import sfx as A_SFX

ROOT = pathlib.Path(__file__).resolve().parents[2]


# ── التفويض هو **نفس الكائن**، مش نسخة ─────────────────────────────
@pytest.mark.parametrize("mod,name,origin", [
    (shared.captions, "render_caption", A_CAP), (shared.captions, "pad_to_box", A_CAP),
    (shared.captions, "caption_box", A_CAP),    (shared.captions, "blank_png", A_CAP),
    (shared.captions, "caption_size", A_CAP),   (shared.captions, "available_width", A_CAP),
    (shared.frames, "validate_fps", A_GRAPH),   (shared.frames, "piecewise", A_GRAPH),
    (shared.frames, "offsets_of", A_GRAPH),     (shared.frames, "caption_sequence", A_GRAPH),
    (shared.frames, "caption_frames", A_GRAPH), (shared.frames, "frame_to_sample", A_SFX),
    (shared.frames, "samples_per_frame", A_SFX),
    (shared.probe, "probe", A_CUTS),            (shared.probe, "verify_source", A_CUTS),
    (shared.probe, "check_ffmpeg", A_CUTS),
    (shared.probe, "assert_output_not_mislabelled", A_REN),
])
def test_shared_is_the_same_object(mod, name, origin):
    assert getattr(mod, name) is getattr(origin, name), (
        f"shared.{mod.__name__}.{name} صار نسخة بدل تفويض — "
        f"تعريفان لنفس الشي بيفترقوا بصمت"
    )


# ── `shared/` ما بتعرّف منطقًا ──────────────────────────────────────
def test_shared_defines_only_the_glue():
    """الدوال المسموح تعريفها بـ`shared/` معدودة بالاسم.

    أي دالة جديدة بتنعرّف هون لازم تنضاف لهالقائمة **بقصد** — الفحص
    بيفشل قبلها، فالتوسّع بينصير قرارًا مش انزلاقًا.
    """
    allowed = {"exe"}
    defined = set()
    for f in sorted((ROOT / "shared").glob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined.add(node.name)
            if isinstance(node, ast.ClassDef):
                defined.add(node.name)
    assert defined == allowed, (
        f"`shared/` بتعرّف {sorted(defined - allowed)} — التفويض بيتحوّل "
        f"لتنفيذ. انقل المنطق لطرفه، أو ضيف الاسم للقائمة بقصد."
    )


# ── الاتجاه واحد: autoreel ما بتعرف عن shared ولا عن ai_pipeline ────
@pytest.mark.parametrize("mod", ["captions", "cuts", "graph", "render",
                                 "sfx", "exports", "transcribe", "cli"])
def test_editor_never_imports_the_new_subsystems(mod):
    """لو `autoreel` استوردت `shared` بيصير الحدّ دائرة، والمحرر بيرث
    تبعيات التوليد (pydantic) بلا سبب."""
    src = (ROOT / "autoreel" / f"{mod}.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for n in names:
            top = n.split(".")[0]
            assert top not in {"shared", "ai_pipeline"}, (
                f"autoreel/{mod}.py بيستورد {n} — الحدّ اتجاهه واحد")


def test_ai_pipeline_reaches_the_editor_only_through_shared():
    """`ai_pipeline` ممنوع تستورد `autoreel` مباشرة."""
    for f in sorted((ROOT / "ai_pipeline").rglob("*.py")):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for n in names:
                assert n.split(".")[0] != "autoreel", (
                    f"{f.relative_to(ROOT)} بيستورد {n} مباشرة — "
                    f"مرّ عبر shared/")


# ── الثابت المشترك فعلًا مشترك ──────────────────────────────────────
def test_output_model_uses_the_editor_fps_rule():
    """`Output` ما بتعيد شرط `sr % fps`، بتناديه."""
    src = (ROOT / "ai_pipeline" / "models" / "project.py").read_text(encoding="utf-8")
    assert "validate_fps" in src
    assert "sample_rate % self.fps" not in src, "الشرط انتنسخ بدل ما ينتنادى"
