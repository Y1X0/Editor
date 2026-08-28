"""
باني رسم الفلتر للمسار الواحد — **دوال نقية، بلا تشغيل**.

أرقام وإعدادات داخل، نص خارج. ولا نداء ffmpeg هون، فكل قرار بالرسم
بينفحص بلا ترميز. `render.py` هي اللي بتشغّل.

المرجع الكامل ومبرّرات كل قرار: `REDESIGN-SPEC.md`. الخلاصة العملية:

    [0:v] fps=FPS, select='…', settb=1/FPS, setpts=N, fps=FPS

**الأربعة إلزاميين وبالترتيب هاد.** كل واحد فيهن ثمن لغم مقاس:

* `fps` الأولى: بتضمن CFR قبل ما نعتمد على `n` كفهرس إطار. بدونها `n`
  رقم الإطار المفكوك، وهو بيفترق عن فهرس الشبكة مع مصدر VFR.
* `settb=1/FPS` ثم `setpts=N`: **مش** `setpts=N/FPS/TB`. التانية بتحسب
  بعائمة، وعند `tbn=15360` بتطلع N·512 أحيانًا `100863.99999999999`
  فبتنقصّ لصحيح أقل، والـ`fps` اللي بعدها بتحطّ الإطار بالخانة السابقة:
  **إسقاط إطار وتكرار تاني مع بقاء العدد صحيح**. مقاس ٢ من ٣٣٦.
* `fps` التانية: `setpts` بتمسح معدّل الإطارات، فffmpeg بيرجع لافتراضه
  ٢٥ و`-fps_mode cfr` بيعيد التشكيل — ٦٠٠ إطار بتصير ٥٠١.
  و`-fps_mode passthrough` **مش** بديل: بيعطي محتوى صح بس الحاوية
  بتعلن 30.09fps.
"""

DEFAULT_SR = 48000


# ------------------------------------------------------------- تحقّقات

def validate_fps(fps, sr=DEFAULT_SR):
    """
    الصوت بينقصّ على حدود إطارات الفيديو، فلازم الحدّ يطلع عدد عيّنات
    **صحيح**: `sr % fps == 0`.

    ٢٤ و٢٥ و٣٠ و٥٠ و٦٠ بتزبط مع 48kHz. معدّلات NTSC الكسرية (29.97،
    59.94) لأ — و`atrim` وقتها بتقرّب بصمت وبينزاح الصوت.
    """
    if isinstance(fps, float) and not float(fps).is_integer():
        raise ValueError(
            f"output.fps = {fps} كسري. المسار الواحد بيقصّ الصوت على حدود "
            f"الإطارات، وهاد بده عدد عيّنات صحيح لكل إطار. "
            f"استعمل معدّلًا صحيحًا (٢٤ · ٢٥ · ٣٠ · ٥٠ · ٦٠).")
    fps = int(fps)
    if fps <= 0:
        raise ValueError(f"output.fps = {fps} — لازم يكون موجبًا")
    if sr % fps:
        raise ValueError(
            f"sample_rate={sr} ما بينقسم على fps={fps} "
            f"({sr / fps:.4f} عيّنة/إطار). حدود الصوت رح تتقرّب وبينزاح.")
    return fps


def start_frames(segs, fps):
    """بداية كل مقطع كـ**فهرس إطار** بالمصدر."""
    return [max(0, round(a * fps)) for a, _ in segs]


def assert_disjoint(starts, plan):
    """
    مدايات `select` لازم تكون منفصلة.

    `select` بتمرّر إطار المصدر **مرة وحدة** مهما تداخلت المدايات، فتداخل
    مدايتين بيعطي إطارات أقل من `Σ n_i` **بصمت**. `segments_from_words`
    بتدمج المتداخلة أصلًا، بس الرسم صار يعتمد على هالضمانة فلازم تنفحص.
    """
    for i in range(len(starts) - 1):
        end = starts[i] + plan[i]
        if end > starts[i + 1]:
            raise ValueError(
                f"مدايات select متداخلة عند المقطع {i}: "
                f"[{starts[i]}, {end}) و[{starts[i+1]}, …). "
                f"مجموع الإطارات رح يطلع أقل من الخطة بصمت.")


# ------------------------------------------------------------- تعابير

def select_expr(starts, plan):
    """`between(n,s,e)+…` — مدايات مغلقة من الطرفين، فالمدى = `n` إطار."""
    return "+".join(f"between(n,{s},{s + n - 1})" for s, n in zip(starts, plan))


def piecewise(values, offsets, plan, var="n"):
    """
    `Σ v_i · between(n, a_i, b_i)` — بالضبط حدّ واحد بيشتغل لكل `n`.

    مجموع **مسطّح** مش `if` متداخلة: عند ٣٠٠ مقطع التداخل بيصير ٣٠٠
    مستوى. وآخر مقطع بيمتد لرقم كبير كأمان — لو طلب المرمِّز إطارًا بعد
    الآخر، المجموع بيضل قيمة صالحة بدل صفر (وصفر بـ`scale` = خطأ).

    الفاصلة مهروبة (`\\,`) لأن الفلتر بيفصل وسائطه بالفاصلة.
    """
    if not (len(values) == len(offsets) == len(plan)):
        raise ValueError("piecewise: أطوال مش متساوية")
    last = len(values) - 1
    out = []
    for i, v in enumerate(values):
        a = offsets[i]
        b = 9_999_999 if i == last else offsets[i] + plan[i] - 1
        out.append(f"{v}*between({var}\\,{a}\\,{b})")
    return "+".join(out)


def offsets_of(plan):
    """بداية كل مقطع بالمخرَج."""
    return [sum(plan[:i]) for i in range(len(plan))]


# --------------------------------------------------------------- الجذع

def video_stem(fps, starts, plan, out_label="stem"):
    """`[0:v]` -> تيار مقصوص ومرقّم على شبكة الإطارات."""
    assert_disjoint(starts, plan)
    return (f"[0:v]fps={fps},select='{select_expr(starts, plan)}',"
            f"settb=1/{fps},setpts=N,fps={fps}[{out_label}]")


def split_chain(src_label, labels):
    """`split` لتغذية عدة مقاسات. مع مقاس واحد بيرجّع إعادة تسمية."""
    if len(labels) == 1:
        return f"[{src_label}]null[{labels[0]}]"
    return (f"[{src_label}]split={len(labels)}"
            + "".join(f"[{x}]" for x in labels))


DEFAULT_SPEECH_GAIN = 0.70


def sfx_chain(cues, inputs, in_label="acat", out_label="amixed",
              speech_gain=DEFAULT_SPEECH_GAIN, sr=DEFAULT_SR,
              total_samples=None):
    """
    مزج المؤثرات على الصوت المقصوص. **دالة نقية — نص داخل، نص برّا.**

    `cues`   = `[autoreel.sfx.Cue]` — **المصدر الوحيد للتخطيط.** هالوحدة
               ما بتختار أحداثًا ولا بتصفّي؛ كل هاد بـ`sfx.py`.
    `inputs` = `{اسم الأصل: فهرس مدخَل ffmpeg}`.

    الشكل، وكل جزء فيه مقيس (`SFX-SPEC.md` §A.3/§A.4):

        [k:a] aformat=sample_rates=SR:channel_layouts=stereo   ← مرة لكل أصل
              [, asplit=n]                                     ← إعادة استعمال
        [x]   volume=<كسب الحدث>, adelay=<فهرس العيّنة>S:all=1  ← لكل مؤثر
        [acat]volume=<كسب الكلام>
        [spk][s0][s1]… amix=inputs=N+1:duration=first:normalize=0

    **الترتيب مش تجميليًا:**

    * `aformat` **قبل** `adelay` — `adelay=NS` بتعدّ عيّنات بمعدّل
      **المدخَل**. أصل 44.1k بلاها بيقع بعد ٥٢٢٤٥ عيّنة بدل ٤٨٠٠٠،
      يعني **+٨٨ms**، بلا أي تحذير من ffmpeg.
    * `all=1` إلزامية — بدونها `adelay` بتأخّر **القناة الأولى بس**
      والتانية بتضل مكانها، فالمؤثر بيقع عند العيّنة **٠** (خطأ
      −٤٨٠٠٠). صامتة كمان.
    * `normalize=0` إلزامية — الافتراضية بتقسّم كل مدخل على عددهن،
      فالكلام بيخفت لـ٠.١١× عند ٢٠ مؤثرًا **وبيتنفّس** مع انتهاء كل
      مؤثر. معها: ٠ عيّنة كلام متغيّرة.
    * `adelay` **مطلقة لكل مؤثر** — مش سلسلة تأخيرات متتابعة. فالخطأ
      ما بيتراكم بالبناء: آخر مؤثر بنفس دقة أوّلهن.

    **كسب الكلام ٠.٧٠ ثابت مش مقيسًا.** المصدر ≤١.٠ بالتعريف، فالضرب
    بـ٠.٧٠ بيضمن ذروة ≤٠.٧٠ بلا أي تمريرة تحليل. مع أعلى ذروة أصل
    (٠.٩٠) وكسب ٠.٢٥: ٠.٧٠ + ٠.٩٠×٠.٢٥ = **٠.٩٢٥ < ١.٠** — الهامش
    مضمون بالحساب مش بالحظ.

    ولا `alimiter`: مقيس إنه بيأخّر التيار **٢٣٩ عيّنة (٤.٩٨ms)**،
    فبيرجّع E2 من ١.٩٨ms لـ~٥ms.

    **`total_samples` بتثبّت الطول بالبناء — ولا تشيلها.**

    `apad,atrim=end_sample=N` بعد `amix`. بدونها الطول بيعتمد على
    دلالة `duration` بـ`amix`، **وهاي بتفرق بين نسخ ffmpeg**: على
    7.0.2 عنا `duration=first` بتعطي الطول الصح، وعلى 6.1.1 بتعطي
    **١٢٨٠ عيّنة أقل** (٢٦.٧ms) — الصوت بينقصّ بصمت والأداة بتقول
    "تمّ بنجاح".

    مع التثبيت الطول مضبوط بكل الحالات، متحقَّق بمحاكاة `amix` مكسورة:

        duration=first     -> 384000 ✅
        duration=longest   -> 384000 ✅
        duration=shortest  -> 384000 ✅   (بدون التثبيت: 68080)

    وما بيغيّر ولا عيّنة لما الطول أصلًا صحيح (فرق ٠.٠٠٠٠٠٠٠٠).

    نفس مبدأ المشروع: **الطول قرارنا مش قرار الفلتر** — زي
    `-frames:v N` بالفيديو و`atrim` بفهرس العيّنة بالصوت.
    """
    if not cues:
        raise ValueError("ولا مؤثر — الاستدعاء نفسه غلط، شوف `audio_chain`")
    missing = sorted({c.asset for c in cues} - set(inputs))
    if missing:
        raise ValueError(f"أصول بلا مدخَل: {missing}")

    order = []
    for c in cues:
        if c.asset not in order:
            order.append(c.asset)

    parts, branches = [], {}
    for ai, asset in enumerate(order):
        n = sum(1 for c in cues if c.asset == asset)
        labels = [f"x{ai}_{j}" for j in range(n)]
        head = (f"[{inputs[asset]}:a]"
                f"aformat=sample_rates={sr}:channel_layouts=stereo")
        # `asplit=1` صالحة بس بلا معنى — الأصل المستعمل مرة وحدة ما بينقسم.
        if n == 1:
            parts.append(f"{head}[{labels[0]}]")
        else:
            parts.append(f"{head},asplit={n}" + "".join(f"[{x}]" for x in labels))
        branches[asset] = list(labels)

    tags = []
    for i, c in enumerate(cues):
        src = branches[c.asset].pop(0)
        tag = f"s{i}"
        parts.append(f"[{src}]volume={c.gain:.4f},"
                     f"adelay={c.sample}S:all=1[{tag}]")
        tags.append(tag)

    parts.append(f"[{in_label}]volume={speech_gain:.4f}[spk]")
    mix = (f"amix=inputs={len(tags) + 1}:duration=first:normalize=0")
    if total_samples is not None:
        mix += f",apad,atrim=end_sample={int(total_samples)}"
    parts.append("[spk]" + "".join(f"[{t}]" for t in tags)
                 + mix + f"[{out_label}]")
    return parts


def audio_chain(fps, starts, plan, out_labels, sr=DEFAULT_SR,
                cues=None, sfx_inputs=None,
                speech_gain=DEFAULT_SPEECH_GAIN):
    """
    `atrim` على حدود الإطارات، ثم `concat`، ثم نسخة لكل مخرَج.

    `atrim` بتقصّ على مستوى **العيّنة**؛ `aselect` بتقصّ على مستوى إطار
    الترميز (١٠٢٤ عيّنة ≈ ٢١ms) فبتعطي ضجيج ±٢١ms. والتخزين رخيص:
    الصوت مونو-مكافئ ≈٩٦ KB/s مقابل إطارات فيديو.

    **`start_sample`/`end_sample` مش `start=`/`end=` بالثواني** — بس
    لأسباب بنيوية، مش لأننا قِسنا خللًا بالثواني:

    الثواني بتمرق على `%.9f` ثم على تحليل مدّة، و`37/30` بتنطبع
    `1.233333333` = ٥٩١٩٩.٩٨٤ عيّنة. قِسنا الاتنين على ٤٠ مقطع:
    **النتيجة متطابقة** — أقصى انزياح ١.٩٨ms (أرضية القياس) وتراكم صفر
    للاتنين، ومجموع العيّنات ٧٦٨٠٠٠ بالضبط للاتنين. يعني تقريب ffmpeg
    الداخلي بيمتصّ الفرق اليوم.

    فليش الفهرس؟ لأن الضبط بيصير **بالبناء** بدل ما يعتمد على تفاصيل
    طباعة عشرية وتحليل مدّة داخل ffmpeg — نفس مبدأ `select` بفهرس
    الإطار، مطبَّقًا على الصوت. الفرق مش مقاس اليوم، والمكسب إنه ما
    بيقدر يظهر بكرا.

    ما في ترميز هون: كل شي PCM لحد المخرَج النهائي. ترميز AAC بيصير
    **مرة وحدة لكل ملف**، وهاد اللي بيلغي تراكم priming padding.
    """
    k = len(plan)
    spf = sr // fps                      # عيّنات لكل إطار — صحيح بحكم `validate_fps`
    parts = [f"[0:a]aresample={sr},asplit={k}"
             + "".join(f"[d{i}]" for i in range(k))]
    for i, (s, n) in enumerate(zip(starts, plan)):
        parts.append(f"[d{i}]atrim=start_sample={s * spf}:"
                     f"end_sample={(s + n) * spf},"
                     f"asetpts=PTS-STARTPTS[a{i}]")
    parts.append("".join(f"[a{i}]" for i in range(k))
                 + f"concat=n={k}:v=0:a=1[acat]")

    # المؤثرات بتنمزج **بعد `concat` وقبل التوزيع**: أحداثها معرَّفة
    # على التوقيت النهائي (بعد القص)، وهي مستقلة عن المقاس تمامًا زي
    # الصوت — فبناؤها لكل مخرَج شغل مكرَّر بلا فايدة.
    #
    # وبلا مؤثرات **ما بينضاف ولا فلتر**: المسار بيضل حرفيًا زي ما كان،
    # فالمخرَج بلا SFX متطابق بايت-ببايت مع ما قبل هالمرحلة.
    tail = "acat"
    if cues:
        parts += sfx_chain(cues, sfx_inputs or {}, in_label="acat",
                           out_label="amixed", speech_gain=speech_gain, sr=sr,
                           total_samples=sum(plan) * spf)
        tail = "amixed"

    # قيد حقيقي: كل تسمية مخرَج بالفلتر بتنربط **مرة وحدة**.
    if len(out_labels) == 1:
        parts.append(f"[{tail}]anull[{out_labels[0]}]")
    else:
        parts.append(f"[{tail}]asplit={len(out_labels)}"
                     + "".join(f"[{x}]" for x in out_labels))
    return parts


# ---------------------------------------------------------------- الزوم

def zoom_values(cfg, nseg):
    cm = cfg.get("motion", {})
    cycle = cm["zoom_cycle"] if cm.get("enabled") else [1.0]
    return [cycle[i % len(cycle)] for i in range(nseg)]


def _even(n):
    return int(n / 2) * 2


def zoom_dims(cfg, zooms):
    """أبعاد `scale` لكل مقطع — نفس حساب `render.segment_filter` بالضبط."""
    W, H = cfg["output"]["width"], cfg["output"]["height"]
    return ([_even(W * z) for z in zooms], [_even(H * z) for z in zooms])


def pan_offsets(cfg, zooms):
    """
    إزاحة الـpan لكل مقطع، محدودة بالهامش المتاح فعليًا.

    بدون الحدّ `pan_px=26` مع زوم ١.٠٤ بيطلب x=47 والمدى ٤٢، وffmpeg
    بيقصقصها بصمت فالـpan بيتصرف عشوائي بين المقاسات.
    """
    W = cfg["output"]["width"]
    pan = cfg.get("motion", {}).get("pan_px", 0)
    out = []
    for i, z in enumerate(zooms):
        room = max(0, _even(W * z) - W)
        d = 1 if i % 2 == 0 else -1
        out.append(max(-room // 2, min(room // 2, d * pan)))
    return out


DEFAULT_GEOMETRY = {"fit": "crop", "crop_bias": 0.5, "pad_blur": 24}


def scaled_dims(src_w, src_h, sw, sh):
    """
    أبعاد المصدر بعد `scale=sw:sh:force_original_aspect_ratio=increase`.

    `increase` بتاخد **الأكبر** من نسبتي التغطية وبتقرّب لأقرب صحيح.
    قِسناها على أربع حالات (منها نسب مختلفة عن المخرَج): ٥٦٠×٩٩٨ من
    ٦٤٠×١١٣٨ بتعطي **٥٦١**×٩٩٨، و٦١٤×١٠٩٤ بتعطي **٦١٥**×١٠٩٤ —
    و`round(src·s)` بتطابقهن بالضبط.
    """
    s = max(sw / src_w, sh / src_h)
    return round(src_w * s), round(src_h * s)


def size_chain(cfg, plan, zooms, in_label, out_label, src_w, src_h):
    """
    سلسلة مقاس واحد: زوم لكل مقطع ثم قصّ/تبطين.

    الزوم بينتنفّذ بـ`scale` بتعبير على **فهرس إطار المخرَج** `n`
    و`eval=frame`.

    **المرساة أرقام محسوبة بايثونيًا، مش `(iw-W)/2`.** هاد الفرق الوحيد
    عن `segment_filter`، وهو إجباري:

    `crop` بتقيّم `x`/`y` لكل إطار، بس `iw`/`ih` جواتهن **بتتقيّدوا وقت
    ضبط الوصلة** وما بيتتبّعوا مقاس مدخَل بيتغيّر لكل إطار. قِسناها:
    مع `scale` متغيّر (٥٤٠×٩٦٠ ثم ٦١٥×١٠٩٤) الإطار الناتج من
    `x='(iw-540)/2'` **بيختلف** عن الناتج من الرقم الصحيح ٣٧ — يعني
    `iw` ضلّت ٥٤٠.

    بالمعمارية القديمة ما كانت مشكلة: كل مقطع تشغيلة ffmpeg مستقلة
    بمقاس ثابت، فالتعبير بينتقيّم مرة وحدة على القيمة الصح. المسار
    الواحد بيلغي هالفرضية، فلازم نحسب `increase` عنا — و`scaled_dims`
    مقاسة إنها بتطابق ffmpeg.
    """
    W, H = cfg["output"]["width"], cfg["output"]["height"]
    g = {**DEFAULT_GEOMETRY, **cfg.get("geometry", {})}
    fit = g["fit"]
    off = offsets_of(plan)
    sws, shs = zoom_dims(cfg, zooms)
    dims = [scaled_dims(src_w, src_h, w, h) for w, h in zip(sws, shs)]
    w_ex = piecewise(sws, off, plan)
    h_ex = piecewise(shs, off, plan)

    if fit == "pad":
        # الزوم على الخلفية بس — المقدّمة بتدخل كاملة فوقها.
        # مش punch-in على الشخص، وهاد مقصود (شوف CLAUDE.md).
        bx = piecewise([(iw - W) // 2 for iw, _ in dims], off, plan)
        by = piecewise([(ih - H) // 2 for _, ih in dims], off, plan)
        return (f"[{in_label}]split[bg{out_label}][fg{out_label}]; "
                f"[bg{out_label}]scale=w='{w_ex}':h='{h_ex}':"
                f"force_original_aspect_ratio=increase:eval=frame,"
                f"crop={W}:{H}:x='{bx}':y='{by}',"
                f"gblur=sigma={g['pad_blur']}[bgb{out_label}]; "
                f"[fg{out_label}]scale={W}:{H}:"
                f"force_original_aspect_ratio=decrease:"
                f"force_divisible_by=2[fgs{out_label}]; "
                f"[bgb{out_label}][fgs{out_label}]"
                f"overlay=x=(W-w)/2:y=(H-h)/2,setsar=1[{out_label}]")

    if fit != "crop":
        raise ValueError(f"geometry.fit مش معروف: {fit!r} — المتاح: crop, pad")

    bias = min(1.0, max(0.0, g["crop_bias"]))
    pans = pan_offsets(cfg, zooms)
    xs = [(iw - W) // 2 + dx for (iw, _), dx in zip(dims, pans)]
    ys = [round((ih - H) * bias) for _, ih in dims]
    return (f"[{in_label}]scale=w='{w_ex}':h='{h_ex}':"
            f"force_original_aspect_ratio=increase:eval=frame,"
            f"crop={W}:{H}:x='{piecewise(xs, off, plan)}':"
            f"y='{piecewise(ys, off, plan)}',setsar=1[{out_label}]")


# -------------------------------------------------------------- الكابشن

def caption_frames(caps, fps, total_frames):
    """
    `[(png, بداية_ثواني, نهاية_ثواني)]` -> `[(png, إطار_بداية, إطار_نهاية)]`

    نصف مفتوح `[a, b)`. بعد هالتحويل **الزمن ما بيرجع يظهر بمسار
    الكابشن**: الفهرس هو الزمن.

    الحدود بتتقصّ على `[0, total)` وبتتزحلق للأمام لو تراكبت، فالناتج
    مرتّب وبلا تراكب — `overlay` بتيار واحد ما بيحتمل كابشنين بنفس
    الإطار.
    """
    out, cursor = [], 0
    for png, s, e in caps:
        a = min(total_frames, max(cursor, round(s * fps)))
        b = min(total_frames, max(a + 1, round(e * fps)))
        if a >= total_frames:
            break
        out.append((png, a, b))
        cursor = b
    return out


def caption_sequence(cap_frames, total_frames):
    """
    خريطة إطار -> PNG بطول `total_frames`، أو None وين ما في كابشن.

    هاي اللي بتتحوّل لوصلات رمزية باسم فهرس الإطار
    (`%06d.png`)، فـ`-framerate FPS -i seq/%06d.png` بيصير **حتميًا
    بالبناء**: ما في ولا عملية فاصلة، الفهرس هو الزمن.

    البديل (concat demuxer بمدد) مرفوض: قاعدة زمنه للصور ثابتة على
    ١/٢٥ ثانية، فكل حدّ بينقرّب لمضاعف ٤٠ms = نص إطار عند ٣٠fps.
    """
    seq = [None] * total_frames
    for png, a, b in cap_frames:
        for n in range(max(0, a), min(total_frames, b)):
            seq[n] = png
    return seq


# ------------------------------------------------------------ التجميع

def build_graph(cfg, plan, starts, sizes, src_w, src_h,
                caption_inputs=None, sr=DEFAULT_SR, with_audio=True,
                cues=None, sfx_inputs=None,
                speech_gain=DEFAULT_SPEECH_GAIN):
    """
    الرسم كامل.

    `sizes`  = [(اسم, cfg_المقاس)]
    `caption_inputs` = {اسم: فهرس_المدخَل} لتيارات الكابشن، أو None.
    `with_audio=False` لمصدر بلا تيار صوت — `[0:a]` بتفشّل التشغيلة.
    `cues` = `[sfx.Cue]` من `autoreel.sfx`، و`sfx_inputs` = {أصل: فهرس}.
    بلا صوت ما في مؤثرات: ما في `[acat]` نمزج عليها أصلًا.

    بيرجّع `(نص_الرسم, [(اسم, تسمية_فيديو, تسمية_صوت أو None)])`.
    """
    fps = validate_fps(cfg["output"]["fps"], sr)
    assert_disjoint(starts, plan)
    nseg, nout = len(plan), len(sizes)

    zlabels = [f"z{i}" for i in range(nout)]
    alabels = [f"ao{i}" for i in range(nout)] if with_audio else [None] * nout
    parts = [video_stem(fps, starts, plan), split_chain("stem", zlabels)]
    if with_audio:
        parts += audio_chain(fps, starts, plan, alabels, sr=sr,
                             cues=cues, sfx_inputs=sfx_inputs,
                             speech_gain=speech_gain)

    maps = []
    for i, (name, scfg) in enumerate(sizes):
        zoomed = f"g{i}"
        parts.append(size_chain(scfg, plan, zoom_values(scfg, nseg),
                                zlabels[i], zoomed, src_w, src_h))
        if caption_inputs and name in caption_inputs:
            k = caption_inputs[name]
            W, H = scfg["output"]["width"], scfg["output"]["height"]
            y = int(H * scfg["captions"]["y_ratio"])
            parts.append(f"[{k}:v]fps={fps}[cap{i}]")
            parts.append(f"[{zoomed}][cap{i}]"
                         f"overlay=x=(W-w)/2:y={y}-h/2:eof_action=pass[m{i}]")
            maps.append((name, f"m{i}", alabels[i]))
        else:
            maps.append((name, zoomed, alabels[i]))
    return "; ".join(parts), maps
