"""
فحص نسخة ffmpeg — الحارس اللي ما كان موجودًا.

**الحادثة:** كل أرقام المشروع مقاسة على 7.0.2، وانقال «٧٤١ فحص ناجح»
بلا ذكر النسخة. شغّلها المالك على **6.1.1** فطلعت ٤ فاشلة:

    assert 382720 == 384000

الصوت أقصر ١٢٨٠ عيّنة (٢٦.٧ms) لأن `amix=duration=first` بتحسب الطول
غير بين 6.x و7.x. الأداة كانت بتقول «تمّ بنجاح».

**التصليح انعمل بترتيب مقصود: الطول قبل الفحص.** الطول انتثبّت
بالبناء (`apad,atrim=end_sample=N` — حارسه بـ`test_sfx_graph.py`)،
فالفرق ما عاد يقدر يظهر أصلًا. الفحص هون **شبكة أمان مش الحلّ**:
بيقول للمستخدم إنه برّا اللي انقاس، بدل ما يكتشفه من مخرَج غريب.

القاعدة: **الفحص بيمرق على `ffmpeg` حقيقي بالـ`PATH`.** منركّب سكربت
وهمي بيطبع لافتة نسخة مختارة، عشان الفحص يشمل التحليل والسياسة سوا —
مش السياسة لحالها فوق `ffmpeg_version` مبدَّلة.
"""
import os
import subprocess
import sys

import pytest

from measure import ffmpeg_available

from autoreel import cuts as C

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fake_ffmpeg(tmp_path, banner):
    """`PATH` أوّله `ffmpeg` بيطبع `banner` على stdout. بيرجّع الـPATH."""
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    p = d / "ffmpeg"
    p.write_text(f'#!/bin/sh\necho "{banner}"\n')
    p.chmod(0o755)
    return os.pathsep.join([str(d), os.environ.get("PATH", "")])


def _version_with(tmp_path, banner):
    """`ffmpeg_version()` بعملية منفصلة مع اللافتة المختارة."""
    r = subprocess.run(
        [sys.executable, "-c",
         "from autoreel import cuts as C; print(C.ffmpeg_version())"],
        cwd=ROOT, env=dict(os.environ, PATH=_fake_ffmpeg(tmp_path, banner)),
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-1000:]
    return r.stdout.strip()


# ------------------------------------------------------ تحليل اللافتة

@pytest.mark.parametrize("banner, want", [
    # الأشكال اللي بتطلع من تثبيتات حقيقية
    ("ffmpeg version 7.0.2-static https://johnvansickle.com/ffmpeg/", "(7, 0)"),
    ("ffmpeg version 6.1.1-3ubuntu5 Copyright (c) 2000-2023", "(6, 1)"),
    ("ffmpeg version n7.1 Copyright (c) 2000-2024", "(7, 1)"),
    ("ffmpeg version 4.4.2-0ubuntu0.22.04.1", "(4, 4)"),
    # بناء git بلا رقم نسخة — `None` مقصودة: ما منخمّن رقمًا ما انقرا.
    ("ffmpeg version 2024-01-01-git-abcdef123", "None"),
    ("ffmpeg version N-113411-gd21134a", "None"),
])
def test_the_banner_is_parsed_the_way_real_builds_print_it(tmp_path, banner, want):
    assert _version_with(tmp_path, banner) == want


def test_an_unreadable_version_is_none_not_a_guess(tmp_path):
    assert _version_with(tmp_path, "something else entirely") == "None"


# ------------------------------------------------------------ السياسة

def _check_with(tmp_path, banner):
    """`check_ffmpeg` مع تحذير بيطلع على stdout. بيرجّع `CompletedProcess`."""
    return subprocess.run(
        [sys.executable, "-c",
         "from autoreel import cuts as C;"
         "print(C.check_ffmpeg(warn=lambda m: print('WARN:', m)))"],
        cwd=ROOT, env=dict(os.environ, PATH=_fake_ffmpeg(tmp_path, banner)),
        capture_output=True, text=True, timeout=60)


def test_below_the_minimum_raises_instead_of_running(tmp_path):
    """
    تحت 6.0 في فلاتر منعتمد عليها ممكن ما تكون موجودة أصلًا. الفشل
    الصريح أوضح من مخرَج غريب — وهاد بالضبط الدرس من 6.1.1.
    """
    r = _check_with(tmp_path, "ffmpeg version 5.1.4 Copyright (c)")
    assert r.returncode != 0
    assert "5.1" in r.stderr and "6.0" in r.stderr


def test_between_the_minimum_and_the_verified_warns_but_runs(tmp_path):
    """6.1.1 — النسخة اللي كسرت فعلًا. بتشتغل، بس المستخدم بيعرف."""
    r = _check_with(tmp_path, "ffmpeg version 6.1.1-3ubuntu5")
    assert r.returncode == 0, r.stderr[-1000:]
    assert "WARN:" in r.stdout and "6.1" in r.stdout and "7.0" in r.stdout
    assert r.stdout.strip().endswith("(6, 1)")


def test_the_verified_version_is_silent(tmp_path):
    r = _check_with(tmp_path, "ffmpeg version 7.0.2-static")
    assert r.returncode == 0, r.stderr[-1000:]
    assert "WARN:" not in r.stdout


def test_an_unreadable_version_does_not_block_the_run(tmp_path):
    """
    بناء git بلا رقم: ما منقدر نحكم، وما منوقف. منع تشغيلة صحيحة
    بسبب لافتة ما انقرات أسوأ من التحذير اللي ما انطبع.
    """
    r = _check_with(tmp_path, "ffmpeg version N-113411-gd21134a")
    assert r.returncode == 0, r.stderr[-1000:]
    assert "WARN:" not in r.stdout
    assert r.stdout.strip() == "None"


# ------------------------------------------------------------- الوصل

@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg مش موجود")
def test_the_real_ffmpeg_here_is_at_or_above_the_verified_version():
    """
    أرقام هالطقم مقاسة على `VERIFIED_FFMPEG`. لو فشل هالفحص عندك،
    **مش خللًا بالكود** — نتيجتك بتنذكر مع نسختك.
    """
    v = C.ffmpeg_version()
    assert v is not None, "ما انقرات نسخة ffmpeg"
    if v < C.VERIFIED_FFMPEG:
        pytest.skip(f"ffmpeg {v[0]}.{v[1]} — أرقام الطقم مقاسة على "
                    f"{C.VERIFIED_FFMPEG[0]}.{C.VERIFIED_FFMPEG[1]}+")
    assert v >= C.VERIFIED_FFMPEG


def test_the_cli_actually_calls_the_check(tmp_path):
    """
    حارس الوصل: `check_ffmpeg` موجودة بس مين بيناديها؟

    بلا هالفحص، شيل السطر من `cli.main` وكل فحوص السياسة فوق بتضل
    خضراء — نفس شكل الخلل اللي فرض `test_config_wiring` (مفتاح
    مقروء بس مفصول عن الكود).

    ffmpeg الوهمي بيطبع نسخة قديمة وبس؛ فلو الفحص انشال بيكمّل المسار
    ويفشل بشي تاني — لهيك المطلوب **الرسالة** مش مجرد كود خروج ≠ ٠.
    """
    r = subprocess.run(
        [sys.executable, "-m", "autoreel.cli", "لا-يهم.mp4", "-o", str(tmp_path / "o.mp4")],
        cwd=ROOT, env=dict(os.environ, PATH=_fake_ffmpeg(tmp_path, "ffmpeg version 5.1.4")),
        capture_output=True, text=True, timeout=120)
    assert r.returncode != 0
    assert "5.1" in r.stderr and "قديم" in r.stderr, r.stderr[-1500:]
