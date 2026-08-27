"""تجميع الفيديو النهائي: قص + زوم لكل مقطع + حرق الكابشن."""
import shutil, subprocess, sys, tempfile, os, shlex

from . import captions as CAP
from . import cuts as C
from . import graph as G
from .cuts import frame_plan


def preview(cmd):
    """الأمر كنص جاهز للصق بالترمنال."""
    return " ".join(shlex.quote(c) for c in cmd)


def _report(total, label):
    """طابع تقدّم بيكتب على stderr وبيتحدّث عند تغيّر النسبة بس."""
    state = {"pct": -1}

    def show(done):
        pct = min(100, int(done * 100 / total)) if total else 0
        if pct != state["pct"]:
            state["pct"] = pct
            print(f"\r  {label} {pct:3d}%  ({done}/{total} إطار)",
                  end="", file=sys.stderr, flush=True)

    def done():
        if state["pct"] >= 0:
            print("", file=sys.stderr, flush=True)

    return show, done


def run(cmd, dry_run=False, total_frames=None, label=""):
    """
    ينفّذ أمر ffmpeg.

    `dry_run=True` بيطبع الأمر وبيرجع بدون تنفيذ. باقي المنطق —
    خطة القص، الهندسة، رسم الكابشن، أسماء الملفات — بيشتغل عادي،
    فالمطبوع هو الأمر الحقيقي مش تقريب إله. هيك بتنفحص طبقة الفيديو
    من طرف لطرف بلا ffmpeg.

    `total_frames` بيشغّل `-progress pipe:1`: ffmpeg بيكتب `frame=N`
    لstdout مع كل تقدّم، وبما إن **العدد النهائي معروف مسبقًا** من خطة
    الإطارات، بتطلع نسبة حقيقية مش تخمين. هاد ممكن هلأ بس لأن المخرَج
    صار تشغيلة وحدة؛ قبلها كان الشغل مقسومًا على عشرات العمليات.

    stderr بينكتب لملف مؤقت مش لأنبوب: القراءة من stdout وstderr سوا
    بلا خيوط بتتعلّق لو امتلأ أحدهما، وffmpeg بيكتب stderr غزير عند
    الفشل.
    """
    if dry_run:
        print("$ " + preview(cmd))
        return None
    if total_frames:
        cmd = cmd[:1] + ["-progress", "pipe:1", "-nostats"] + cmd[1:]

    show, finish = _report(total_frames, label) if total_frames else (None, None)
    with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as err:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE if total_frames else None,
                             stderr=err, text=True)
        try:
            if total_frames:
                for line in p.stdout:
                    if line.startswith("frame="):
                        try:
                            show(int(line.split("=", 1)[1]))
                        except ValueError:
                            pass
            code = p.wait()
        except BaseException:
            # مقاطعة (Ctrl-C) أو أي خطأ: لا تخلّي ffmpeg شغّالًا ورا ظهرك
            p.kill()
            p.wait()
            if finish:
                finish()
            raise
        finally:
            if p.stdout:
                p.stdout.close()
        if finish:
            finish()
        if code != 0:
            err.seek(0)
            tail = "\n".join(err.read().splitlines()[-20:])
            raise RuntimeError(f"ffmpeg فشل ({code}):\n{preview(cmd[:12])}...\n{tail}")
    return code


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


SFX_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "assets", "sfx")


def sfx_asset(name):
    """
    مسار أصل المؤثر. الفشل هون **أوضح** من رسالة ffmpeg عن مدخَل ناقص،
    وبيصير قبل ما ينبني الرسم أصلًا.
    """
    p = os.path.join(SFX_DIR, f"{name}.wav")
    if not os.path.isfile(p):
        raise RuntimeError(f"أصل مؤثر ناقص: {p}\n"
                           f"شغّل: python assets/sfx/build_assets.py")
    return p


def probe_source(path):
    """
    `(عرض, ارتفاع, فيه_صوت)` — واجهة رفيعة فوق `cuts.probe`.

    `graph.size_chain` بتحسب مرساة القصّ من أبعاد المصدر (لأن `crop.iw`
    ما بتتتبّع مقاسًا متغيّرًا)، ومسار الصوت لازم يعرف إذا في تيار صوت
    أصلًا.

    القراءة نفسها بـ`cuts.probe` مش هون: نسختان من تحليل مخرَج
    `ffmpeg -i` بتنفرقا. وهناك مش هون لأن `render` بتستورد `cuts`،
    فالعكس بيعمل دورة استيراد.
    """
    return probe_source_full(path)[:3]


def probe_source_full(path):
    """`(عرض, ارتفاع, فيه_صوت, مدة)` — النداء الواحد كامل."""
    return C.probe(path)


def materialise_captions(cap_frames, total_frames, outdir):
    """
    تسلسل صور **مفهرس بالإطار**: لكل إطار مخرَج ملف اسمه فهرس الإطار.

    بيرجّع نمط المسار (`…/%06d.png`) الجاهز لـ
    `-framerate FPS -start_number 0 -i <نمط>`.

    ليش وصلات رمزية مش نسخ: الPNG الواحد بيتكرّر عبر كل إطارات كابشنه،
    والنسخ بيضاعف القرص بعدد الإطارات. الوصلة ≈٣٢ بايت — قِسنا ١٠٨٠٠
    وصلة = ٣٣٨ KiB بـ٠.٦٩s.

    fallback للنسخ لما نظام الملفات ما بيدعم الوصلات (بعض تخزين أندرويد
    المشترك). بنجرّب مرة وحدة مش لكل ملف: ١٠٨٠٠ محاولة استثناء بطيئة.

    **ليش مش `concat` demuxer:** قاعدة زمنه للصور ثابتة على ١/٢٥ ثانية،
    فكل حدّ كابشن بينقرّب لمضاعف ٤٠ms = نص إطار عند ٣٠fps. قِسناها:
    خُمس الكابشنات كانت تبلّش إطارًا بدري.
    """
    os.makedirs(outdir, exist_ok=True)
    seq = G.caption_sequence(cap_frames, total_frames)

    # **كل صور التسلسل لازم تكون بنفس المقاس.** تسلسل الصور بياخد أبعاد
    # التيار من أول ملف، وأي تغيّر بالنص بيقطع المخرَج: صور ٤٠٧×٢٠٨
    # و٤٠٨×٢٠٨ (فرق بكسل واحد) أعطت ٧٣ إطار من ١٤٤.
    #
    # التبطين بيصير **مرة لكل كابشن مميّز** مش لكل إطار، فبتضل الوصلات
    # هي اللي بتغطي التكرار.
    box = CAP.caption_box(sorted({p for p in seq if p}))
    padded = {}
    pad_dir = os.path.join(outdir, "box")
    os.makedirs(pad_dir, exist_ok=True)
    for i, png in enumerate(sorted({p for p in seq if p})):
        padded[png] = CAP.pad_to_box(png, os.path.join(pad_dir, f"{i:05d}.png"), box)
    blank = None
    if any(p is None for p in seq):
        blank = CAP.blank_png(os.path.join(pad_dir, "blank.png"), box)

    use_symlink = True
    for n, png in enumerate(seq):
        dst = os.path.join(outdir, f"{n:06d}.png")
        target = os.path.abspath(padded[png] if png is not None else blank)
        if use_symlink:
            try:
                os.symlink(target, dst)
                continue
            except (OSError, NotImplementedError, AttributeError):
                use_symlink = False      # نظام ملفات ما بيدعمها — كمّل نسخًا
        shutil.copy2(target, dst)
    return os.path.join(outdir, "%06d.png")


def build_output(src, segs, caps, cfg, out_path, workdir,
                 dry_run=False, src_info=None, cues=None,
                 speech_gain=G.DEFAULT_SPEECH_GAIN):
    """
    المخرَج النهائي كامل — صورة وصوت وكابشن — بتشغيلة ffmpeg **وحدة**.

        [0:v] fps, select='between(n,…)', settb=1/fps, setpts=N, fps
              -> scale(eval=frame) لكل مقطع -> crop
        [0:a] aresample, asplit, atrim بفهرس العيّنة, asetpts, concat
        [1:v] تسلسل صور مفهرس بالإطار -> overlay واحد

    التلاتة بينقصّوا على **نفس** خطة الإطارات، فما بيقدروا ينفصلوا.
    ولا ترميز وسيط: الصوت بيضل PCM لحد المخرَج (ترميز AAC مرة وحدة)،
    والصورة ما بتنرمّز إلا مرة.

    الكابشن **overlay واحد** مش سلسلة لكل كابشن: السلسلة بتاكل الذاكرة
    مع العدد (قِسنا ٩٤١ MiB عند ٤٠ كابشن و٢٧٧١ MiB عند ٢٠٠)، والتسلسل
    المفهرس ثابت عند ~٨٠ MiB.

    الرسم بينكتب لملف وبينمرّر بـ`-filter_complex_script`: عند ٣٠٠ مقطع
    بيوصل عشرات الكيلوبايتات، وحدود سطر الأوامر على أندرويد أضيق من
    لينكس. وفايدة تانية: بيضل قابلًا للفحص مع `--keep`.
    """
    fps = G.validate_fps(cfg["output"]["fps"])
    plan = frame_plan(segs, fps)
    starts = G.start_frames(segs, fps)
    total = sum(plan)
    sw, sh, has_audio = src_info or probe_source(src)

    name = os.path.basename(workdir) or "out"
    inputs = ["-i", str(src)]
    nin = 1                                   # المصدر ياخد الفهرس ٠
    caption_inputs = None
    if caps:
        # الزمن بينتحوّل لفهارس إطارات **هون**، وبعدها ما بيرجع يظهر
        # بمسار الكابشن أبدًا: الفهرس هو الزمن.
        seq = materialise_captions(G.caption_frames(caps, fps, total), total,
                                   os.path.join(workdir, "seq"))
        inputs += ["-framerate", str(fps), "-start_number", "0", "-i", seq]
        caption_inputs = {name: nin}
        nin += 1

    # **مدخَل لكل أصل مميّز، مش لكل مؤثر.** `graph.sfx_chain` بتقسّمه
    # بـ`asplit` على استعمالاته — مقيس إنه بيوفّر ٣٤–٣٨٪ ذاكرة ووقت.
    # وبلا صوت بالمصدر ما في `[acat]` نمزج عليها، فالمؤثرات بتنطفي.
    sfx_inputs = None
    if cues and has_audio:
        sfx_inputs = {}
        for asset in sorted({c.asset for c in cues}):
            sfx_inputs[asset] = nin
            inputs += ["-i", sfx_asset(asset)]
            nin += 1
    else:
        cues = None

    graph, maps = G.build_graph(cfg, plan, starts, [(name, cfg)], sw, sh,
                                caption_inputs=caption_inputs,
                                with_audio=has_audio,
                                cues=cues, sfx_inputs=sfx_inputs,
                                speech_gain=speech_gain)
    gpath = os.path.join(workdir, "graph.txt")
    with open(gpath, "w", encoding="utf-8") as f:
        f.write(graph)
    if dry_run:
        # `-filter_complex_script` بيخبّي الرسم عن سطر الأمر، و`--dry-run`
        # عقده إنك تشوف اللي رح ينفَّذ بالضبط. فبنطبعه.
        print(f"# {gpath}\n{graph}")

    _, vlabel, alabel = maps[0]
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs,
           "-filter_complex_script", gpath, "-map", f"[{vlabel}]"]
    if alabel:
        cmd += ["-map", f"[{alabel}]"]
    cmd += ["-c:v", "libx264", "-crf", str(cfg["output"]["crf"]),
            "-preset", "veryfast", "-pix_fmt", "yuv420p"]
    if alabel:
        cmd += ["-c:a", "aac", "-b:a", "128k", "-ar", str(G.DEFAULT_SR), "-ac", "2"]
    # كتابة ذرّية: ffmpeg بيكتب لملف `.part`، وما بينتقل للاسم النهائي
    # إلا بعد كود خروج صفر. قِسنا إن قتل ffmpeg بنص التشغيل بيخلّي
    # mp4 **بلا moov** — ملف بشكل مخرَج وهو تالف، وهاد أخطر من الفشل
    # نفسه لأنه بينكتشف بعد الرفع.
    #
    # الامتداد بيضل `.mp4`: ffmpeg بيختار المُغلِّف من الامتداد، و
    # `out.mp4.part` بترمي خطأ "مغلِّف مجهول".
    root, ext = os.path.splitext(str(out_path))
    part = f"{root}.part{ext}"
    cmd += ["-movflags", "+faststart", part]
    try:
        run(cmd, dry_run=dry_run, total_frames=None if dry_run else total,
            label=name)
    except BaseException:
        # الفشل والمقاطعة سوا: ولا ملف بيضل بشكل مخرَج.
        if os.path.exists(part):
            try:
                os.remove(part)
            except OSError:
                pass
        raise
    if not dry_run:
        os.replace(part, str(out_path))
    return out_path
