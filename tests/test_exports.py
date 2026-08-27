"""دمج إعدادات التصدير واختيار المقاسات وتسمية المخرجات."""
import json

import pytest

from autoreel import exports as X
from conftest import ROOT


@pytest.fixture
def root():
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


# ----------------------------------------------------------------- resolve

def test_override_wins(root):
    c = X.resolve(root, "square")
    assert (c["output"]["width"], c["output"]["height"]) == (1080, 1080)


def test_unmentioned_keys_are_inherited(root):
    c = X.resolve(root, "square")
    assert c["output"]["fps"] == root["output"]["fps"]
    assert c["output"]["crf"] == root["output"]["crf"]
    assert c["captions"]["font"] == root["captions"]["font"]
    assert c["captions"]["highlight"] == root["captions"]["highlight"]


def test_empty_export_is_the_root(root):
    c = X.resolve(root, "reel")
    for section in ("output", "captions", "cuts", "motion", "geometry"):
        assert c[section] == root[section]


def test_exports_section_is_stripped_from_the_result(root):
    assert "exports" not in X.resolve(root, "reel")


def test_root_is_not_mutated(root):
    before = json.dumps(root, sort_keys=True)
    X.resolve(root, "square")
    X.resolve(root, "wide")
    assert json.dumps(root, sort_keys=True) == before


def test_sizes_do_not_leak_into_each_other(root):
    """الباگ الكلاسيكي: «الإعداد تسرّب من المقاس اللي قبله»."""
    a = X.resolve(root, "square")
    a["captions"]["size"] = 999
    a["output"]["width"] = 4
    b = X.resolve(root, "square")
    assert b["captions"]["size"] != 999 and b["output"]["width"] != 4


def test_scalars_replace_they_do_not_merge(root):
    root["exports"]["square"]["output"]["crf"] = 28
    assert X.resolve(root, "square")["output"]["crf"] == 28


@pytest.mark.parametrize("key", X.SHARED_KEYS["output"])
def test_overriding_a_shared_key_is_rejected(root, key):
    """
    `output.fps` بيحدّد شبكة الإطارات اللي بينبني عليها توقيت الكابشن،
    وهي محسوبة مرة وحدة لكل المقاسات. دهسها بتصدير بيخلي توقيت هداك
    المقاس مبنيًا على شبكة تانية بلا ما يحس حدا.
    """
    root["exports"]["square"]["output"][key] = 24
    with pytest.raises(ValueError, match=key):
        X.resolve(root, "square")


def test_list_override_replaces_whole_list(root):
    root["exports"]["square"]["geometry"] = {"pad_blur": 9}
    c = X.resolve(root, "square")
    assert c["geometry"]["pad_blur"] == 9
    assert c["geometry"]["fit"] == root["geometry"]["fit"]     # الباقي بيرث


def test_unknown_export_lists_what_exists(root):
    with pytest.raises(KeyError, match="reel"):
        X.resolve(root, "vertical")


@pytest.mark.parametrize("section", X.SHARED)
def test_overriding_a_shared_section_is_rejected(root, section):
    """خطة القص والحركة بتنحسبوا مرة — دهسهن بيوهم بأثر ما إله وجود."""
    root["exports"]["square"][section] = {"whatever": 1}
    with pytest.raises(ValueError, match=section):
        X.resolve(root, "square")


def test_overriding_a_section_that_does_not_exist_is_rejected(root):
    root["exports"]["square"]["captoins"] = {"size": 10}       # غلط مطبعي
    with pytest.raises(KeyError, match="captoins"):
        X.resolve(root, "square")


# ------------------------------------------------------------------ select

def test_default_is_the_first_export_only(root):
    assert X.select(root, None) == ["reel"]


def test_all_returns_every_export_in_order(root):
    assert X.select(root, "all") == list(root["exports"])


def test_explicit_list(root):
    assert X.select(root, "square,wide") == ["square", "wide"]


def test_whitespace_is_tolerated(root):
    assert X.select(root, " square , wide ") == ["square", "wide"]


def test_duplicates_collapse(root):
    assert X.select(root, "reel,reel,square") == ["reel", "square"]


def test_unknown_size_is_rejected(root):
    with pytest.raises(KeyError, match="square"):
        X.select(root, "square,tiktok")


def test_empty_spec_is_rejected(root):
    with pytest.raises(ValueError):
        X.select(root, "  ,  ")


# ------------------------------------------------------------- output_path

def test_single_size_keeps_the_name_the_user_typed():
    assert X.output_path("out.mp4", "reel", multi=False) == "out.mp4"
    assert X.output_path("نشر/reel.mp4", "wide", multi=False) == "نشر/reel.mp4"


def test_multi_suffixes_every_size():
    assert X.output_path("out.mp4", "reel", True) == "out.reel.mp4"
    assert X.output_path("out.mp4", "square", True) == "out.square.mp4"


def test_suffix_keeps_the_directory():
    assert X.output_path("/a/b/reel.mp4", "wide", True) == "/a/b/reel.wide.mp4"


def test_missing_extension_gets_mp4():
    assert X.output_path("out", "reel", True) == "out.reel.mp4"


def test_names_never_collide(root):
    picked = X.select(root, "all")
    paths = [X.output_path("out.mp4", n, True) for n in picked]
    assert len(set(paths)) == len(paths)
