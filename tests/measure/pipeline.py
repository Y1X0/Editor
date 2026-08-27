"""
تشغيل مسار الإنتاج الحقيقي من الاختبارات، والتقاط الخطة اللي استعملها.

**بنشغّل `cli.main()` نفسها**، مش إعادة كتابة لخطواتها. أي اختبار قبول
بيعيد بناء الخطة بنفسه بيوافق حاله ويغلط مع الواقع — نفس الدرس اللي
طلع من `test_config_wiring.py`.
"""
import contextlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def srt_time(t):
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", ",")


def write_srt(path, cues):
    """`cues` = [(start, end, "نص")]"""
    out = []
    for i, (a, b, text) in enumerate(cues, start=1):
        out.append(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{text}\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    return path


def shrink_config(dst, width, height, **over):
    """
    الconfig الحقيقي بأبعاد أصغر — الترميز باختبارات القبول لازم يكون
    ثواني مش دقايق. البنية بتضل نفسها فـ`exports.resolve` بتنفحص كمان.
    """
    cfg = json.loads(open(os.path.join(ROOT, "config.json"), encoding="utf-8").read())
    cfg["captions"]["font"] = os.path.join(ROOT, cfg["captions"]["font"])
    cfg["output"]["width"], cfg["output"]["height"] = width, height
    for k, v in over.items():
        a, b = k.split(".")
        cfg[a][b] = v
    for name, ov in cfg.get("exports", {}).items():
        ov.pop("width", None)
        ov.pop("height", None)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False)
    return dst


def _duration_via_ffmpeg(path):
    r = subprocess.run(["ffmpeg", "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    if not m:
        raise RuntimeError(f"ما قدرت أقرا مدة {path}")
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


@contextlib.contextmanager
def flat_captions(color_of):
    """
    بيخلّي `render_caption` تطلّع **لون مصمت** بدل النص، بنفس المقاس
    بالضبط.

    ليش: E3 اختبار **توقيت** مش رسم. الشكل مغطّى بالصور المرجعية.
    باستبدال البكسلات وحدها بنضل نمرق على `group_words` و`_fit`
    و`build_caption_pngs` وجسر الفجوة — يعني كل قرار توقيت — وبنكسب
    قراءة الكابشن من أي بكسل بدل مطابقة نص عربي مكبّر.

    `color_of(index)` بترجّع RGB للكابشن رقم index بترتيب `caps`.
    """
    from autoreel import captions as CAP
    real = CAP.render_caption
    seen = {"n": 0}

    def fake(text, cfg, W, highlight_idx=None):
        img = real(text, cfg, W, highlight_idx=highlight_idx)
        c = color_of(seen["n"])
        seen["n"] += 1
        from PIL import Image
        return Image.new("RGBA", img.size, tuple(c) + (255,))

    CAP.render_caption = fake
    try:
        yield seen
    finally:
        CAP.render_caption = real


def run_pipeline(input_path, out_path, config, srt=None, sizes=None, extra=()):
    """
    بيشغّل `autoreel.cli.main()` وبيرجّع dict فيه اللي المسار قرّره فعلًا:
      segs, fps, plan, offsets, durations, caps, rc

    الخطة بتنلتقط **من نداء الإنتاج نفسه** (تجسّس على `cuts.frame_plan`)
    مش بإعادة حسابها هون.
    """
    from autoreel import captions as CAP
    from autoreel import cli as CLI
    from autoreel import cuts as C

    rec = {"segs": None, "fps": None, "plan": None, "caps": []}

    real_plan = C.frame_plan
    real_caps = CAP.build_caption_pngs
    real_dur = C.probe_duration

    def spy_plan(segs, fps):
        n = real_plan(segs, fps)
        if rec["plan"] is None:            # نداء cli، مش نداء render لكل مقاس
            rec["segs"], rec["fps"], rec["plan"] = list(segs), fps, list(n)
        return n

    def spy_caps(*a, **k):
        out = real_caps(*a, **k)
        rec["caps"].append(list(out))
        return out

    def dur(path):
        try:
            return real_dur(path)
        except (FileNotFoundError, OSError):
            # ffprobe مش موجود بكل بيئة. المدة مش الشي المفحوص هون،
            # والخطة بتنلتقط من الإنتاج مهما كانت.
            return _duration_via_ffmpeg(path)

    C.frame_plan, CAP.build_caption_pngs, C.probe_duration = spy_plan, spy_caps, dur
    argv = sys.argv
    sys.argv = ["autoreel.cli", str(input_path), "-o", str(out_path),
                "-c", str(config), *(["--srt", str(srt)] if srt else []),
                *(["--sizes", sizes] if sizes else []), *extra]
    try:
        rc = CLI.main()
    finally:
        sys.argv = argv
        C.frame_plan, CAP.build_caption_pngs, C.probe_duration = (
            real_plan, real_caps, real_dur)

    assert rec["plan"] is not None, "ما انلتقطت خطة إطارات — المسار ما اشتغل"
    plan = rec["plan"]
    return {
        "rc": rc,
        "segs": rec["segs"],
        "fps": rec["fps"],
        "plan": plan,
        "total": sum(plan),
        "offsets": [sum(plan[:i]) for i in range(len(plan))],
        "durations": [n / rec["fps"] for n in plan],
        "caps": rec["caps"][0] if rec["caps"] else [],
    }


def segment_of(offsets, plan, n):
    for i, off in enumerate(offsets):
        if off <= n < off + plan[i]:
            return i
    return None
