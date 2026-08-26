"""تجميع الفيديو النهائي: قص + زوم لكل مقطع + حرق الكابشن."""
import subprocess, os, shlex


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


def build_base(src, segs, cfg, workdir, dry_run=False):
    """
    يقص المقاطع، يطبّق زوم مختلف لكل مقطع (punch-in)، ويلزقهم.
    الزوم ثابت داخل المقطع — هيك بيطلع الشكل المعروف بالريلز.
    """
    W = cfg["output"]["width"]; H = cfg["output"]["height"]
    fps = cfg["output"]["fps"]
    cycle = cfg["motion"]["zoom_cycle"] if cfg["motion"]["enabled"] else [1.0]
    pan = cfg["motion"].get("pan_px", 0)

    parts = []
    for i, (a, b) in enumerate(segs):
        z = cycle[i % len(cycle)]
        dx = (pan if i % 2 == 0 else -pan) if z > 1.001 else 0
        sw, sh = int(W * z / 2) * 2, int(H * z / 2) * 2
        vf = (f"scale={sw}:{sh}:force_original_aspect_ratio=increase,"
              f"crop={W}:{H}:(iw-{W})/2+{dx}:(ih-{H})/2,"
              f"fps={fps},setsar=1")
        out = os.path.join(workdir, f"seg{i:04d}.mp4")
        run(["ffmpeg", "-y", "-loglevel", "error",
             "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", src,
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
