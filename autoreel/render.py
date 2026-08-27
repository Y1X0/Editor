"""تجميع الفيديو النهائي: قص + زوم لكل مقطع + حرق الكابشن."""
import subprocess, os, shlex

from .cuts import frame_plan


def preview(cmd):
    """الأمر كنص جاهز للصق بالترمنال."""
    return " ".join(shlex.quote(c) for c in cmd)


def run(cmd, quiet=True, dry_run=False):
    """
    ينفّذ أمر ffmpeg.

    `dry_run=True` بيطبع الأمر وبيرجع بدون تنفيذ. باقي المنطق —
    خطة القص، الهندسة، رسم الكابشن، أسماء الملفات — بيشتغل عادي،
    فالمطبوع هو الأمر الحقيقي مش تقريب إله. هيك بتنفحص طبقة الفيديو
    من طرف لطرف بلا ffmpeg.
    """
    if dry_run:
        print("$ " + preview(cmd))
        return None
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg فشل:\n{preview(cmd[:12])}...\n{r.stderr[-1800:]}")
    return r


DEFAULT_GEOMETRY = {"fit": "crop", "crop_bias": 0.5, "pad_blur": 24}


def _even(n):
    """ffmpeg بده أبعاد زوجية مع yuv420p."""
    return int(n / 2) * 2


def segment_filter(cfg, zoom=1.0, pan_dir=0):
    """
    سلسلة الفلاتر لمقطع واحد. دالة نقية — نص داخل، نص خارج — عشان
    تنختبر بلا ffmpeg. شوف tests/test_geometry.py

    `fit="crop"`: كبّر ليغطّي الإطار وقصّ. `crop_bias` بتحرّك نافذة
    القص عموديًا: ٠.٥ = المركز (السلوك القديم)، وأقل = لفوق. لازمة
    لأن القص من المركز بياخد وسط الإطار وبيقصّ الوجه.

    `fit="pad"`: صغّر ليدخل الإطار كامل، وعبّي الفراغ بنسخة مكبّرة
    مموّهة. ولا بكسل بينقص. هاد الصح لما تغيّر النسبة حاد — 16:9 من
    مصدر عمودي بياخد ٣١.٦٪ من الارتفاع بالقص، وهاد إتلاف مش قص.

    `pan_dir`: ‎+1 / ‎-1 / 0. المقدار من `motion.pan_px` — الـpan حركة
    مش هندسة، فمكانه هناك. بينحدّ بالهامش المتاح فعليًا: بدون الحدّ
    `pan_px=26` مع زوم ١.٠٤ بيطلب x=47 والمدى ٤٢، وffmpeg بيقصقصها
    بصمت فالـpan بيتصرف عشوائي بين المقاسات.
    """
    W = cfg["output"]["width"]; H = cfg["output"]["height"]
    fps = cfg["output"]["fps"]
    g = {**DEFAULT_GEOMETRY, **cfg.get("geometry", {})}
    fit = g["fit"]

    sw, sh = _even(W * zoom), _even(H * zoom)

    if fit == "pad":
        # الخلفية بتغطي الإطار وبتتموّه؛ المقدّمة بتدخل **كاملة** فوقها.
        #
        # المقدّمة بتتقاس على W×H مش على sw×sh: الزوم بينطبق على
        # الخلفية بس. لو كبّرنا المقدّمة معها بترجع تنقصّ — وهاد بيلغي
        # سبب وجود `pad` أصلًا. يعني ما في punch-in على الشخص بهالنمط،
        # وهاد مقصود: فيديو مبطّن والشخص بينطّ فيه شكله رديء.
        blur = g["pad_blur"]
        return (f"split[bg][fg];"
                f"[bg]scale={sw}:{sh}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},gblur=sigma={blur}[bgb];"
                f"[fg]scale={W}:{H}:force_original_aspect_ratio=decrease:"
                f"force_divisible_by=2[fgs];"
                f"[bgb][fgs]overlay=x=(W-w)/2:y=(H-h)/2,"
                f"fps={fps},setsar=1")

    if fit != "crop":
        raise ValueError(f"geometry.fit مش معروف: {fit!r} — المتاح: crop, pad")

    # المدى المتاح للحركة داخل الإطار المكبّر، ومنه بينحدّ كل شي.
    room_x = max(0, sw - W)
    pan = cfg.get("motion", {}).get("pan_px", 0)
    dx = max(-room_x // 2, min(room_x // 2, pan_dir * pan))

    bias = min(1.0, max(0.0, g["crop_bias"]))
    # `increase` ممكن يكبّر أكتر من sw/sh لو النسبة اختلفت، فالمرساة
    # لازم تنحسب بتعابير ffmpeg على الأبعاد الفعلية مش على أرقامنا.
    x = f"(iw-{W})/2{dx:+d}"
    y = f"(ih-{H})*{bias:.4f}"
    return (f"scale={sw}:{sh}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H}:{x}:{y},"
            f"fps={fps},setsar=1")


def preview_frame(src, at, cfg, out_path, caption_png=None, dry_run=False):
    """
    إطار PNG واحد بهندسة هالمقاس، بلا ترميز فيديو.

    وجودها لأن `geometry.crop_bias` بينضبط على تأطير فيديوك إنت. رقم
    واحد ما بيزبط لكل التأطيرات، والمستخدم لازم يشوف نافذة القص قبل
    ما يصرف دقايق ترميز على مقاس بيقصّ الوجه.
    """
    cycle = cfg["motion"]["zoom_cycle"] if cfg["motion"]["enabled"] else [1.0]
    vf = segment_filter(cfg, zoom=cycle[0], pan_dir=1)

    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{at:.3f}", "-i", src]
    if caption_png:
        y = int(cfg["output"]["height"] * cfg["captions"]["y_ratio"])
        cmd += ["-i", caption_png, "-filter_complex",
                f"[0:v]{vf}[base];[base][1:v]overlay=x=(W-w)/2:y={y}-h/2"]
    else:
        cmd += ["-vf", vf]
    cmd += ["-frames:v", "1", out_path]
    run(cmd, dry_run=dry_run)
    return out_path


def build_base(src, segs, cfg, workdir, dry_run=False):
    """
    يقص المقاطع، يطبّق زوم مختلف لكل مقطع (punch-in)، ويلزقهم.
    الزوم ثابت داخل المقطع — هيك بيطلع الشكل المعروف بالريلز.
    """
    cycle = cfg["motion"]["zoom_cycle"] if cfg["motion"]["enabled"] else [1.0]
    fps = cfg["output"]["fps"]
    nframes = frame_plan(segs, fps)

    parts = []
    for i, ((a, b), n) in enumerate(zip(segs, nframes)):
        z = cycle[i % len(cycle)]
        vf = segment_filter(cfg, zoom=z, pan_dir=(1 if i % 2 == 0 else -1))
        out = os.path.join(workdir, f"seg{i:04d}.mp4")
        # `-frames:v` بدل `-to`: بيحدّد المدة بعدد إطارات بدل زمن
        # بيقرّبه ffmpeg كيف ما بده. شوف `cuts.frame_plan` للقياس.
        run(["ffmpeg", "-y", "-loglevel", "error",
             "-ss", f"{a:.3f}", "-i", src, "-frames:v", str(n),
             "-vf", vf, "-c:v", "libx264", "-crf", str(cfg["output"]["crf"]),
             "-preset", "veryfast", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
             "-avoid_negative_ts", "make_zero", out], dry_run=dry_run)
        parts.append(out)

    lst = os.path.join(workdir, "concat.txt")
    with open(lst, "w") as f:
        for p in parts:
            f.write(f"file '{os.path.abspath(p)}'\n")
    base = os.path.join(workdir, "base.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", lst, "-c", "copy", base], dry_run=dry_run)
    return base


def burn_captions(base, caps, cfg, out_path, batch=60, workdir=None, dry_run=False):
    """
    يحرق الكابشن على دفعات — تجنّبًا لسلسلة overlay طويلة بتكسر ffmpeg
    أو بتاكل الذاكرة على الموبايل.

    `workdir` = وين تنكتب ملفات التمرير الوسيطة. مرّر مجلد العمل المؤقت
    من `cli.py`. بدونه بتنكتب جنب ملف الإخراج.

    لا تستعمل `os.path.dirname(out_path)` لحاله: مع `-o out.mp4` بترجّع
    `""` فالملفات بتنكتب بمجلد الشغل وبتضل هناك بعد ما البرنامج يخلص.
    """
    if not caps:
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", base,
             "-c", "copy", out_path], dry_run=dry_run)
        return out_path

    H = cfg["output"]["height"]
    y = int(H * cfg["captions"]["y_ratio"])
    cur = base
    tmpdir = workdir or os.path.dirname(os.path.abspath(out_path))
    stale = None            # تمريرة سابقة صارت غير لازمة

    for bi in range(0, len(caps), batch):
        chunk = caps[bi:bi + batch]
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", cur]
        for p, _, _ in chunk:
            cmd += ["-i", p]
        fc, last = [], "0:v"
        for k, (_, s, e) in enumerate(chunk, start=1):
            tag = f"v{k}"
            fc.append(f"[{last}][{k}:v]overlay=x=(W-w)/2:y={y}-h/2:"
                      f"enable='between(t,{s:.3f},{e:.3f})'[{tag}]")
            last = tag
        final = bi + batch >= len(caps)
        nxt = out_path if final else os.path.join(tmpdir, f"pass{bi:05d}.mp4")
        cmd += ["-filter_complex", ";".join(fc), "-map", f"[{last}]",
                "-map", "0:a?", "-c:v", "libx264", "-crf", str(cfg["output"]["crf"]),
                "-preset", "veryfast", "-pix_fmt", "yuv420p",
                "-c:a", "copy", "-movflags", "+faststart", nxt]
        run(cmd, dry_run=dry_run)
        # التمريرة السابقة انقرأت خلص. كل واحدة فيديو كامل، فتركهن
        # بيضاعف استهلاك القرص مع كل دفعة.
        if stale and not dry_run:
            try:
                os.remove(stale)
            except OSError:
                pass
        stale = None if final else nxt
        cur = nxt
    return out_path
