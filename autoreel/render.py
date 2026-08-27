"""تجميع الفيديو النهائي: قص + زوم لكل مقطع + حرق الكابشن."""
import re, subprocess, os, shlex

from . import graph as G
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


def probe_size(path):
    """
    أبعاد أول تيار فيديو، عبر `ffmpeg -i` مش `ffprobe`.

    ليش مش ffprobe: `graph.size_chain` بتحسب مرساة القصّ من أبعاد
    المصدر (لأن `crop.iw` ما بتتتبّع مقاسًا متغيّرًا)، فصار المسار
    بيلزمه هالرقم بكل تشغيلة. و`ffmpeg` موجود بالتعريف بينما `ffprobe`
    ممكن يكون ناقصًا بتثبيتات ثابتة.
    """
    r = subprocess.run(["ffmpeg", "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Stream #\d+:\d+.*?: Video:.*?, (\d+)x(\d+)", r.stderr)
    if not m:
        raise RuntimeError(f"ما قدرت أقرا أبعاد الفيديو من {path}")
    return int(m.group(1)), int(m.group(2))


def build_video(src, segs, cfg, workdir, dry_run=False, src_size=None):
    """
    الفيديو بتشغيلة ffmpeg **وحدة**، والقصّ بفهرس الإطار مش بالزمن.

        [0:v] fps, select='between(n,…)', settb=1/fps, setpts=N, fps
              -> scale(eval=frame) لكل مقطع -> crop

    الزوم بينتنفّذ بتعبير على فهرس إطار المخرَج، فما في `split` لكل مقطع
    وما في ترميز وسيط. `graph.py` بيبني النص والمبرّرات هناك.

    الرسم بينكتب لملف وبينمرّر بـ`-filter_complex_script`: عند ٣٠٠ مقطع
    بيوصل عشرات الكيلوبايتات، وحدود سطر الأوامر على أندرويد أضيق من
    لينكس. وفايدة تانية: بيضل قابلًا للفحص مع `--keep`.
    """
    fps = G.validate_fps(cfg["output"]["fps"])
    plan = frame_plan(segs, fps)
    starts = G.start_frames(segs, fps)

    sw, sh = src_size or probe_size(src)
    graph = "; ".join([
        G.video_stem(fps, starts, plan, out_label="stem"),
        G.size_chain(cfg, plan, G.zoom_values(cfg, len(segs)), "stem", "vout",
                     sw, sh),
    ])
    gpath = os.path.join(workdir, "graph.txt")
    with open(gpath, "w", encoding="utf-8") as f:
        f.write(graph)
    if dry_run:
        # `-filter_complex_script` بيخبّي الرسم عن سطر الأمر، و`--dry-run`
        # عقده إنك تشوف اللي رح ينفَّذ بالضبط. فبنطبعه.
        print(f"# {gpath}\n{graph}")

    out = os.path.join(workdir, "video.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", src,
         "-filter_complex_script", gpath, "-map", "[vout]",
         "-c:v", "libx264", "-crf", str(cfg["output"]["crf"]),
         "-preset", "veryfast", "-pix_fmt", "yuv420p", out], dry_run=dry_run)
    return out


def _legacy_audio(src, segs, cfg, workdir, dry_run=False):
    """
    **سقالة مؤقتة — المرحلة ٦ بتشيلها بالكامل.**

    مسار الصوت القديم بحاله: ترميز AAC لكل مقطع ثم `concat -c copy`.
    الأوامر **ما تغيّرت ولا حرف** عن قبل، عن قصد: هيك بينضل انزياح
    الصوت المتراكم مطابقًا تمامًا، فأي تغيّر بقياس E2 بيصير دليلًا إني
    لمست شيئًا ما كان لازم ألمسه.

    الثمن ترميز فيديو ضايع لكل مقطع. مقبول لمرحلة وحدة، وبيروح مع
    المرحلة ٦.
    """
    cycle = cfg["motion"]["zoom_cycle"] if cfg["motion"]["enabled"] else [1.0]
    fps = cfg["output"]["fps"]
    nframes = frame_plan(segs, fps)

    parts = []
    for i, ((a, b), n) in enumerate(zip(segs, nframes)):
        z = cycle[i % len(cycle)]
        vf = segment_filter(cfg, zoom=z, pan_dir=(1 if i % 2 == 0 else -1))
        out = os.path.join(workdir, f"seg{i:04d}.mp4")
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
    out = os.path.join(workdir, "audio.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", lst, "-c", "copy", out], dry_run=dry_run)
    return out


def build_base(src, segs, cfg, workdir, dry_run=False, src_size=None):
    """
    المقطع المقصوص المزوّم، صورة وصوت.

    الصورة من `build_video` (تشغيلة وحدة، قصّ بفهرس الإطار)، والصوت من
    `_legacy_audio` (المسار القديم، سقالة للمرحلة ٥ وبس).

    `-map 1:a?` اختياري: مصدر بلا صوت بيمرق بدل ما يفشل.
    """
    video = build_video(src, segs, cfg, workdir, dry_run=dry_run,
                        src_size=src_size)
    audio = _legacy_audio(src, segs, cfg, workdir, dry_run=dry_run)
    base = os.path.join(workdir, "base.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-i", audio,
         "-map", "0:v", "-map", "1:a?", "-c", "copy", "-shortest", base],
        dry_run=dry_run)
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
