"""
حراس التغليف — `pyproject.toml` وملفات التبعيات والرخص.

**ليش أصلًا:** التبعيات صارت مكتوبة بمكانين (`pyproject.toml` و
`requirements*.txt`)، وإعداد pytest كان بمكانين (`pytest.ini`
و`pyproject.toml`). التكرار الصامت بهالمشروع إله سجلّ: `motion.pan_px`
انفصلت عن قارئها والـpan صار صفرًا بصمت، و١٩٠ فحص هندسة ما مسكوها.

فالقاعدة نفسها متطبَّقة على التغليف: **مصدر واحد، وحارس بيمسك
الافتراق.** `pytest.ini` انحذف (pyproject بيغلب عليه أصلًا لما يكون
`[tool.pytest.ini_options]` موجودًا — فوجود الاتنين معناه ملف بيتعدّل
وما بيأثر). و`requirements*.txt` ضلّت لأن README بينادي عليها، بس
هالفحص بيلزمها تطابق `pyproject`.
"""
import os
import re

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # < 3.11
    tomllib = pytest.importorskip("tomli")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    return open(os.path.join(ROOT, name), encoding="utf-8").read()


@pytest.fixture(scope="module")
def proj():
    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
        return tomllib.load(f)


def _reqs(name):
    """أسطر ملف تبعيات، بلا فراغ ولا تعليق."""
    return [l.strip() for l in _read(name).splitlines()
            if l.strip() and not l.startswith("#")]


# ------------------------------------------------------- مصدر واحد

def test_requirements_txt_matches_the_declared_dependencies(proj):
    assert sorted(_reqs("requirements.txt")) == sorted(proj["project"]["dependencies"])


def test_requirements_dev_matches_the_dev_extra(proj):
    want = proj["project"]["optional-dependencies"]["dev"]
    assert sorted(_reqs("requirements-dev.txt")) == sorted(want)


def test_pytest_is_configured_in_exactly_one_place(proj):
    """
    `pytest.ini` بيغلب عليه `pyproject` لما يكون فيه
    `[tool.pytest.ini_options]` — فوجود الاتنين معناه ملف بيتعدّل وما
    بيأثر. هاد شكل نفس الخلل اللي فرض `test_config_wiring`.
    """
    assert not os.path.exists(os.path.join(ROOT, "pytest.ini"))
    assert not os.path.exists(os.path.join(ROOT, "setup.cfg"))
    assert "ini_options" in proj["tool"]["pytest"]


def test_every_marker_used_in_the_suite_is_declared(proj):
    """
    علامة غير معلَنة بتصير تحذيرًا مش خطأ، و`-m "not slow"` بتصفّي
    على اسم ما بيطابق ولا شي — يعني بتشتغل التقيلة وأنت فاكر إنها
    متخطّاة.
    """
    declared = {m.split(":")[0] for m in proj["tool"]["pytest"]["ini_options"]["markers"]}
    used = set()
    d = os.path.join(ROOT, "tests")
    for name in os.listdir(d):
        if name.endswith(".py"):
            used |= set(re.findall(r"pytest\.mark\.(\w+)",
                                   open(os.path.join(d, name), encoding="utf-8").read()))
    builtin = {"parametrize", "skipif", "skip", "xfail", "usefixtures", "filterwarnings"}
    assert (used - builtin) <= declared, f"علامات غير معلَنة: {(used - builtin) - declared}"


# ------------------------------------------------------------- الرخص

def test_the_project_carries_a_license(proj):
    """
    بلا ملف رخصة، «مفتوح المصدر» ادعاء بلا أثر قانوني — الحقوق
    محفوظة افتراضيًا ولا حدا بيقدر يستعمله.
    """
    assert proj["project"]["license"] == "MIT"
    assert "Permission is hereby granted" in _read("LICENSE")


def test_the_bundled_font_carries_its_own_license():
    """
    MIT بجذر المستودع بتغطّي **الكود**. Tajawal تحت OFL 1.1 وشروطها
    مختلفة، فتوزيعها بلا نصّ رختها مخالفة — والملفات موجودة بالمستودع.
    """
    ofl = _read("fonts/OFL.txt")
    assert "SIL OPEN FONT LICENSE" in ofl.upper()
    assert os.path.exists(os.path.join(ROOT, "fonts", "Tajawal-ExtraBold.ttf"))


# ------------------------------------------------------------- PKG-1

def test_no_entry_point_while_the_data_lives_outside_the_package(proj):
    """
    **حارس PKG-1.** `config.json` و`fonts/` و`assets/sfx/` برّا حزمة
    `autoreel`، فما بينتشحنوا مع `pip install`. أمر `autoreel` مثبَّت
    بينكسر برّا جذر المستودع.

    الحارس مشروط مش مطلق: حطّ البيانات جوا الحزمة، وحطّ الentry point
    وقتها. اللي ممنوع هو الوعد اللي ما بينشتغل.
    """
    has_script = bool(proj["project"].get("scripts"))
    data_inside = all(os.path.exists(os.path.join(ROOT, "autoreel", p))
                      for p in ("config.json", "fonts", "assets"))
    assert not has_script or data_inside, (
        "في `[project.scripts]` وبيانات التشغيل لسا برّا الحزمة — "
        "الأمر المثبَّت بينكسر. شوف ISSUES.md / PKG-1.")


def test_the_wheel_is_buildable_and_carries_the_license(tmp_path):
    """
    بناء حقيقي مش قراءة toml: `pyproject` بيتحلّل بس ما بيبني كتير.
    وبيثبّت كمان الادعاء اللي بـPKG-1 — البيانات مش جوا العجلة.
    """
    build = pytest.importorskip("build", reason="حزمة build مش مثبتة")
    del build
    import subprocess
    import sys
    import zipfile

    r = subprocess.run([sys.executable, "-m", "build", "--wheel", "-o", str(tmp_path)],
                       cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]

    whl = next(p for p in os.listdir(tmp_path) if p.endswith(".whl"))
    names = zipfile.ZipFile(os.path.join(tmp_path, whl)).namelist()
    assert any(n.startswith("autoreel/") and n.endswith(".py") for n in names)
    assert any(n.endswith("licenses/LICENSE") for n in names), names
    # PKG-1 مقاسة مش مفترَضة
    assert not any("fonts/" in n or "assets/" in n or n.endswith("config.json")
                   for n in names), "البيانات صارت جوا العجلة — حدّث PKG-1"
