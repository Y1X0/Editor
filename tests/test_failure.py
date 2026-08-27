"""
دلالات الفشل والتقدّم.

المسار صار تشغيلة ffmpeg وحدة، وهاد بيغيّر شكل الفشل: بدل ما تخسر
دفعة، بتخسر التشغيلة. المقابل إن **العدد النهائي معروف مسبقًا** من خطة
الإطارات، فصار في نسبة تقدّم حقيقية.

الخطر الأكبر مش الفشل — هو الملف اللي **بيبيّن مخرَجًا وهو تالف**.
قِسناه: قتل ffmpeg بنص التشغيل بيخلّي mp4 بلا `moov`، يعني ملف بحجم
معقول ما بينفتح. بينكتشف بعد الرفع.
"""
import os
import shutil
import sys
import subprocess
import threading
import time

import pytest

from measure import build_source, count_frames, ffmpeg_available
from measure.pipeline import run_pipeline, shrink_config, write_srt

from autoreel import render as R

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg مش موجود"),
]

FPS, OUT_W, OUT_H = 30, 360, 640
CUES = [(2.0 + 2.0 * i - 0.12, 2.0 + 2.0 * i + 0.28, "كلمة تانية تالتة")
        for i in range(6)]


@pytest.fixture(scope="module")
def src(tmp_path_factory):
    return build_source(tmp_path_factory.mktemp("fail_src"),
                        width=320, height=568, fps=FPS, nframes=420)


def _run(src, d, **kw):
    cfg = shrink_config(d / "config.json", OUT_W, OUT_H)
    srt = write_srt(d / "in.srt", CUES)
    return run_pipeline(src["path"], d / "out.mp4", cfg, srt=srt,
                        sizes="reel", **kw)


# ------------------------------------------------------- الكتابة الذرّية

def test_a_successful_run_leaves_only_the_output(src, tmp_path):
    info = _run(src, tmp_path)
    assert info["rc"] == 0
    left = sorted(p.name for p in tmp_path.iterdir())
    assert "out.mp4" in left
    assert not any(".part" in n for n in left), f"ملف جزئي ضلّ: {left}"


def test_the_output_appears_only_after_ffmpeg_succeeds(src, tmp_path,
                                                       monkeypatch):
    """
    الاسم النهائي بينحطّ بـ`os.replace` **بعد** كود الخروج صفر. لو
    انكتب مباشرة، أي فشل بيخلّي mp4 تالفًا بشكل مخرَج سليم.
    """
    seen = {}
    real = R.run

    def spy(cmd, *a, **k):
        # وقت ما ffmpeg شغّال، الاسم النهائي لازم ما يكون موجودًا
        seen["target"] = cmd[-1]
        seen["final_exists_during"] = (tmp_path / "out.mp4").exists()
        return real(cmd, *a, **k)

    monkeypatch.setattr(R, "run", spy)
    _run(src, tmp_path)
    assert seen["target"].endswith(".part.mp4"), seen["target"]
    assert seen["final_exists_during"] is False
    assert (tmp_path / "out.mp4").exists()


def test_a_failing_ffmpeg_leaves_no_output_and_no_part(src, tmp_path,
                                                       monkeypatch):
    """
    بنفشّل ffmpeg بحقن علم غلط. النتيجة لازم تكون: كود خروج ≠ ٠، ولا
    ملف بشكل مخرَج، ولا ملف `.part` مخلّف.

    **هاد فشل بالإقلاع** — ffmpeg بيموت قبل ما يفتح المخرَج، فما في
    جزئي أصلًا وشرط "ما ضلّ .part" بيتحقّق لحاله. الفشل **بعد** فتح
    المخرَج (اللي فيه في شي ينتنظّف فعلًا) بيغطّيه فحص القتل تحت.
    """
    real = R.run

    def broken(cmd, *a, **k):
        return real(list(cmd[:1]) + ["-loglevel", "error", "-xyzzy"] + list(cmd[1:]),
                    *a, **k)

    monkeypatch.setattr(R, "run", broken)
    info = _run(src, tmp_path)
    assert info["rc"] != 0
    left = sorted(p.name for p in tmp_path.iterdir())
    assert "out.mp4" not in left, "ضلّ ملف بشكل مخرَج بعد الفشل"
    assert not any(".part" in n for n in left), f"ملف جزئي ضلّ: {left}"


def test_the_error_message_carries_ffmpeg_own_words(tmp_path):
    """
    رسالة "ffmpeg فشل" لحالها ما بتفيد. لازم يوصل نصّ ffmpeg نفسه —
    وهو بstderr اللي بينكتب لملف مؤقت مش لأنبوب.

    **بنفحص على كلام ffmpeg بس، مش على اسم الملف.** أول صيغة كانت
    بتقبل `"مش-موجود" in ...`، وهاد بيمرق من صدى الأمر نفسه
    (`preview(cmd[:12])`) بلا ما يوصل ولا حرف من stderr — فكانت
    بتنجح حتى لو حوّلنا stderr لأنبوب ما حدا بيقراه.
    """
    with pytest.raises(RuntimeError) as e:
        R.run(["ffmpeg", "-y", "-loglevel", "error", "-i",
               str(tmp_path / "مش-موجود.mp4"), str(tmp_path / "o.mp4")])
    msg = str(e.value)
    assert "ffmpeg فشل" in msg
    assert "No such file" in msg, f"ما وصل نصّ stderr:\n{msg}"


# أنبوب Linux بيسع ٦٤ ك.ب. `-loglevel trace` على ٣٠ ثانية بيطلّع
# ~١٠٢ ك.ب (مقيس)، يعني بيتجاوز السعة أكيد. أقل من هيك ما بيثبت شي:
# ١٢ ثانية بتطلّع ٤٧ ك.ب وبتخلص بلا تعليق حتى مع أنبوب.
CHATTY = ["ffmpeg", "-y", "-loglevel", "trace", "-f", "lavfi", "-i",
          "testsrc=size=320x240:rate=30:duration=30",
          "-c:v", "libx264", "-preset", "ultrafast"]


def test_stderr_never_deadlocks_on_a_chatty_run(tmp_path):
    """
    stderr بينكتب لملف مش لأنبوب: منقرا stdout (التقدّم) بلا خيوط،
    ولو كان stderr أنبوبًا ما حدا بيقراه بيتعلّق أول ما يمتلي.

    بنشغّله **بعملية منفصلة بمهلة**: لو تعلّق فعلًا، الاختبار بيفشل
    بـ`TimeoutExpired` بدل ما يعلّق الجلسة كلها.
    """
    driver = tmp_path / "drive.py"
    driver.write_text(
        "import sys\n"
        f"sys.path.insert(0, {os.path.dirname(os.path.dirname(os.path.abspath(__file__)))!r})\n"
        "from autoreel import render as R\n"
        f"R.run({CHATTY!r} + [{str(tmp_path / 'chatty.mp4')!r}],"
        " total_frames=900, label='t')\n",
        encoding="utf-8")
    r = subprocess.run([sys.executable, str(driver)], timeout=120,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    assert (tmp_path / "chatty.mp4").exists()


# ------------------------------------------------------------ المقاطعة

def test_an_interrupt_is_a_clean_failure(src, tmp_path, monkeypatch):
    """
    Ctrl-C لازم يتصرّف زي الفشل بالضبط: ffmpeg بينقتل، والملف الجزئي
    بينمسح، والاستثناء بيمرق. غير هيك بيضل ffmpeg شغّالًا ورا ظهرك
    وبيضل ملف تالف على القرص.

    **المقاطعة بتنرمى من حلقة قراءة التقدّم، مش من `wait()`.** جرّبنا
    من `wait()` أول مرة وطلعت فاضية: `run()` بيسحب stdout لحد ما
    ينسدّ، يعني `wait()` بينادى بعد ما ffmpeg يكون خلّص، فالـ`kill()`
    بيوقع على عملية ميتة وكود الخروج بيضل صفر. Ctrl-C الحقيقي بيوصل
    وffmpeg لسا شغّال — وهاي اللحظة اللي بتنفحص.

    **وبنفحص على كود الإشارة مش على "خلص".** `poll() is not None`
    بيتحقّق لحاله لأن الرندر أقصر من عمر الاختبار، فحذف `p.kill()`
    من `run()` كان بيمرق سالمًا. كود سالب = انقتل بإشارة.
    """
    real_popen = subprocess.Popen
    holder = {}

    part = tmp_path / "out.part.mp4"

    class CtrlC:
        """
        بديل `p.stdout`: بيرمي `KeyboardInterrupt` بدل ما يقرا سطر
        تقدّم. بيستنّى الملف الجزئي ينفتح الأول عشان يكون في **شي
        ينتنظّف** — بلا هالانتظار المقاطعة بتوقع قبل ما ffmpeg يفتح
        المخرَج، فحذف مسح الجزئي كان بيمرق بلا ما يفشل شي.
        """
        def __init__(self, raw, proc):
            self._raw, self._proc = raw, proc

        def __iter__(self):
            return self

        def __next__(self):
            deadline = time.time() + 20
            while time.time() < deadline:
                if part.exists() and part.stat().st_size > 0:
                    break
                if self._proc.poll() is not None:
                    break
                time.sleep(0.002)
            holder["hit"] = True
            holder["part_existed"] = part.exists()
            holder["alive"] = self._proc.poll() is None
            raise KeyboardInterrupt

        def close(self):
            self._raw.close()

    class Interrupting(real_popen):
        """
        بتقاطع **تشغيلة الرندر بس**. `probe_source` بتستعمل
        `subprocess.run` اللي بتمرق على `Popen` كمان، ولو قاطعناها
        بنكون نفحص شيئًا تانيًا.
        """
        def __init__(self, cmd, *a, **k):
            mine = any("filter_complex_script" in str(x) for x in cmd)
            super().__init__(cmd, *a, **k)
            if mine:
                holder["p"] = self
                self.stdout = CtrlC(self.stdout, self)

    monkeypatch.setattr(R.subprocess, "Popen", Interrupting)
    with pytest.raises(KeyboardInterrupt):
        _run(src, tmp_path)
    assert holder.get("hit"), "ما انقاطعت تشغيلة الرندر"
    assert holder.get("alive"), "ffmpeg كان خلّص قبل المقاطعة"
    assert holder.get("part_existed"), "المقاطعة وقعت قبل ما ينفتح الجزئي"
    rc = holder["p"].poll()
    assert rc is not None, "ffmpeg ضلّ شغّالًا بعد المقاطعة"
    assert rc < 0, f"ffmpeg خلّص لحاله ({rc}) — ما انقتل"
    left = sorted(p.name for p in tmp_path.iterdir())
    assert "out.mp4" not in left and not any(".part" in n for n in left), left


def count_frames_or_none(path):
    try:
        return count_frames(path)
    except Exception:
        return None


def test_killing_ffmpeg_midway_leaves_nothing_playable(src, tmp_path,
                                                       monkeypatch):
    """
    **الحالة اللي كل هالمرحلة موجودة لأجلها — بقتل حقيقي.**

    بنقتل ffmpeg وهو شغّال، وبنمسك نسخة من الملف الجزئي قبل ما
    ينمسح. لازم يطلع:
      ١. العملية كانت **حيّة** لحظة القتل — القتل واقعي مش على جثّة
      ٢. الجزئي موجود، و**غير قابل للقراءة** كفيديو
      ٣. وما ضلّ ولا ملف بالاسم النهائي ولا `.part`

    **القتل بخيط جنبي مش من `wait()`.** `run()` بيسحب التقدّم من
    stdout لحد ما ينسدّ، يعني `wait()` بينادى **بعد** ما ffmpeg يكون
    خلص، فالقتل من هناك بيوقع على عملية ميتة والفحص بيمرق فاضيًا. صار
    معنا: الرندر خلّص ١٠٨/١٠٨ والفحص طلع أخضر بلا ما يقتل ولا شي.

    **قِسنا منحنى نمو الملف الجزئي** (عيّنة كل ٢ms على هالسيناريو):

        0.178s → 0 بايت   (انفتح)
        0.219s → 48       (ftyp بس)
        0.560s → 191823   (كل الباقي دفعة وحدة عند الإغلاق)

    يعني ما في حالة "حجم معقول ومقصوص" نقدر نمسكها بهالمقاس — في
    حالتين بس: ٤٨ بايت أو الملف كامل. فمنقتل عند أول بايت. الخاصية
    اللي بينختبر عليها مش حجم الجزئي، هي إن **ما في ولا لحظة** بيكون
    فيها الاسم النهائي موجودًا وهو ناقص.
    """
    real_popen = subprocess.Popen
    snapshot = tmp_path / "snapshot.bin"
    part = tmp_path / "out.part.mp4"
    holder = {}

    class KillMidway(real_popen):
        def __init__(self, cmd, *a, **k):
            self._mine = any("filter_complex_script" in str(x) for x in cmd)
            super().__init__(cmd, *a, **k)
            if self._mine:
                holder["p"] = self
                threading.Thread(target=self._kill_once_writing,
                                 daemon=True).start()

        def _kill_once_writing(self):
            """أول ما ينزل بايت على القرص — شوف منحنى النمو بالوصف."""
            deadline = time.time() + 20
            while time.time() < deadline:
                if self.poll() is not None:      # خلّص قبل ما نلحقه
                    return
                if part.exists() and part.stat().st_size > 0:
                    holder["killed_at"] = part.stat().st_size
                    holder["was_alive"] = self.poll() is None
                    self.kill()
                    return
                time.sleep(0.002)

    real_remove = os.remove

    def snapping_remove(path):
        if str(path).endswith(".part.mp4") and os.path.exists(path):
            holder["size"] = os.path.getsize(path)
            shutil.copy2(path, snapshot)
        real_remove(path)

    monkeypatch.setattr(R.subprocess, "Popen", KillMidway)
    monkeypatch.setattr(R.os, "remove", snapping_remove)

    info = _run(src, tmp_path)
    assert holder.get("was_alive"), "ما لحقنا نقتله وهو شغّال"
    assert info["rc"] != 0, "القتل ما انعكس على كود الخروج"
    assert holder.get("size", 0) > 0, "ما انمسك ملف جزئي قبل المسح"
    assert count_frames_or_none(str(snapshot)) is None, (
        "الملف الجزئي انقرا كفيديو سليم — المقدّمة انكسرت")
    left = sorted(p.name for p in tmp_path.iterdir())
    assert "out.mp4" not in left, "ضلّ ملف بالاسم النهائي بعد القتل"
    assert not any(n.endswith(".part.mp4") for n in left), left


# -------------------------------------------------------------- التقدّم

def test_progress_is_reported_against_the_frame_plan(src, tmp_path, capsys):
    """
    النسبة مبنية على `Σ n_i` المعروف مسبقًا، مش على تخمين من المدة.
    وهاد صار ممكنًا لأن المخرَج تشغيلة وحدة.
    """
    info = _run(src, tmp_path)
    err = capsys.readouterr().err
    assert "%" in err, "ما انطبع تقدّم"
    assert f"/{info['total']} إطار" in err, err[-200:]
    assert "100%" in err


def test_progress_uses_the_progress_flag_not_stderr_scraping(src, tmp_path,
                                                             monkeypatch):
    seen = {}
    real = R.run

    def spy(cmd, *a, **k):
        seen["cmd"] = cmd
        seen["kw"] = k
        return real(cmd, *a, **k)

    monkeypatch.setattr(R, "run", spy)
    info = _run(src, tmp_path)
    assert seen["kw"].get("total_frames") == info["total"]


def test_dry_run_reports_no_progress(src, tmp_path, capsys):
    """ما في شغل فعلي، فما في تقدّم — والمطبوع يضل الأمر الحقيقي."""
    _run(src, tmp_path, extra=("--dry-run",))
    err = capsys.readouterr().err
    assert "%" not in err
