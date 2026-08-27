"""
خطة المؤثرات الصوتية — **دوال نقية، ولا نداء ffmpeg**.

نفس دور `graph.py` بالضبط بس للصوت: بتاخد أرقامًا وبترجّع أرقامًا،
فبتنفحص كلها بلا ترميز. بناء الرسم ووصله بالإنتاج مرحلة تانية.

## القاعدة اللي كل شي هون مبني عليها

**الحدث معرَّف بفهرس إطار المخرَج، والتزامن الصوتي بفهرس العيّنة.**
ولا زمن عائم بأي مكان. التحويل ضرب صحيح:

    sample = frame × (sr // fps)

`graph.validate_fps` بتضمن `sr % fps == 0` أصلًا (٤٨٠٠٠/٣٠ = ١٦٠٠
عيّنة للإطار)، فما في كسر ولا تقريب ولا تراكم. هاي نفس القاعدة اللي
خلّت الصورة والصوت والكابشن ينقصّوا على **نفس** خطة الإطارات
(`REDESIGN-SPEC.md`)، ومطبَّقة هون على المؤثرات.

القياس اللي بيسندها (`SFX-SPEC.md` §A.2): `adelay` بفهرس العيّنة
(`NS`) صفر خطأ على ٧ أهداف؛ والصيغة اللي بيكتبها الإنسان طبيعيًا —
ميلي صحيح — بتغلط ±٢٣ عيّنة (±٠.٤٨ms).

## مصادر الأحداث

كلها مشتقّة من بنى **موجودة أصلًا**، ولا واحدة بتحتاج تحليل محتوى
ولا نموذج. نفس المدخل بيعطي نفس المخرَج بالضبط.

| الحدث | مصدره |
|---|---|
| `start` | الإطار ٠ |
| `cut` | حدود المقاطع من `frame_plan` التراكمي |
| `zoom` | حدّ مقطع تغيّرت عنده قيمة الزوم |
| `caption` | أول إطار بكل مجموعة كابشن |
| `word` | إطار بداية كل كلمة كاريوكي (**مطفي افتراضيًا**) |
| `finale` | بداية آخر مقطع |
"""

DEFAULT_SR = 48000

# ترتيب الأولوية عند التزاحم — **الأول أقوى**.
#
# لازم يكون ترتيبًا صريحًا لأن التزاحم مش نادرًا: قِسنا على كلام
# واقعي (`SFX-SPEC.md` §C.5) إن **تغيّرات الزوم بتتطابق مع حدود
# المقاطع تمامًا** — ١٥ و١٥ بنفس السيناريو. يعني `cut` و`zoom`
# بينطلقوا على نفس الإطار بشكل منهجي، مش بالصدفة.
PRIORITY = ("start", "finale", "cut", "zoom", "caption", "word")

DEFAULTS = {
    "enabled": True,
    # أقل مسافة بين مؤثرين. مقصودة لمنع إطلاق مؤثرين على نفس اللحظة
    # أو على لحظتين متلاصقتين — شوف `suppress`.
    "min_gap": 0.12,
    # أقصى عدد مؤثرات **شغّالة سوا**. بينحسب من مدد الأصول، فبيحتاج
    # `durations` — بلاها ما بينطبّق (وهاد موثّق مش ضمني).
    "max_concurrent": 3,
    "events": {
        "start":   {"asset": "impact", "gain": 0.30, "enabled": True},
        "finale":  {"asset": "riser",  "gain": 0.22, "enabled": True},
        "cut":     {"asset": "whoosh", "gain": 0.22, "enabled": True},
        "zoom":    {"asset": "whoosh", "gain": 0.18, "enabled": True},
        "caption": {"asset": "pop",    "gain": 0.25, "enabled": True},
        # مطفي افتراضيًا: مقيس ٥٨ مؤثر/دقيقة بدونه، و٢١١ معه.
        "word":    {"asset": "tick",   "gain": 0.12, "enabled": False},
    },
}


class Event:
    """حدث منطقي: إطار ونوع. بلا صوت ولا كسب بعد."""

    __slots__ = ("frame", "kind")

    def __init__(self, frame, kind):
        if kind not in PRIORITY:
            raise ValueError(f"نوع حدث مجهول: {kind!r} — المتاح {PRIORITY}")
        self.frame = int(frame)
        self.kind = kind

    def __eq__(self, other):
        return (isinstance(other, Event)
                and (self.frame, self.kind) == (other.frame, other.kind))

    def __hash__(self):
        return hash((self.frame, self.kind))

    def __repr__(self):
        return f"Event({self.frame}, {self.kind!r})"


class Cue:
    """مؤثر مجدوَل: إطار، **فهرس عيّنة**، أصل، كسب."""

    __slots__ = ("frame", "sample", "kind", "asset", "gain")

    def __init__(self, frame, sample, kind, asset, gain):
        self.frame, self.sample = int(frame), int(sample)
        self.kind, self.asset, self.gain = kind, asset, float(gain)

    def __eq__(self, other):
        return isinstance(other, Cue) and self._key() == other._key()

    def _key(self):
        return (self.frame, self.sample, self.kind, self.asset, self.gain)

    def __hash__(self):
        return hash(self._key())

    def __repr__(self):
        return (f"Cue(frame={self.frame}, sample={self.sample}, "
                f"kind={self.kind!r}, asset={self.asset!r}, gain={self.gain})")


# ------------------------------------------------------------ التحويل

def frame_to_sample(frame, fps, sr=DEFAULT_SR):
    """
    فهرس الإطار -> فهرس العيّنة. **ضرب صحيح، ولا تقريب.**

    بترمي لو `sr` ما بتنقسم على `fps` — لأن الكسر هون بيعني إن
    الحدث ما إله موقع عيّنة واحد، وهاد باب الانزياح اللي المشروع
    صرف مراحل يسدّه.
    """
    if sr % fps:
        raise ValueError(f"{sr} ما بتنقسم على {fps} — ما في فهرس عيّنة صحيح")
    return int(frame) * (sr // fps)


def samples_per_frame(fps, sr=DEFAULT_SR):
    if sr % fps:
        raise ValueError(f"{sr} ما بتنقسم على {fps}")
    return sr // fps


def seconds_to_frames(seconds, fps):
    """
    ثواني -> إطارات، **مرة وحدة عند حدّ التهيئة**.

    الإعدادات بتنكتب بالثواني لأنها مقروءة للإنسان، بس التحويل
    بيصير هون وبس. بعدها كل المنطق بالإطارات — فما في مقارنة عائمة
    بأي مكان بالخطة.
    """
    return max(0, int(round(float(seconds) * fps)))


# -------------------------------------------------------- مصادر الأحداث

def segment_start_frames(plan):
    """أول إطار بكل مقطع — تراكمي من خطة الإطارات."""
    out, acc = [], 0
    for n in plan:
        out.append(acc)
        acc += n
    return out


def cut_frames(plan):
    """حدود المقاطع بدون الإطار ٠ — القطة الأولى مش قطة."""
    return segment_start_frames(plan)[1:]


def zoom_change_frames(plan, zooms):
    """حدود المقاطع اللي تغيّرت عندها قيمة الزوم."""
    if zooms is None:
        return []
    if len(zooms) != len(plan):
        raise ValueError(f"عدد قيم الزوم {len(zooms)} ≠ عدد المقاطع {len(plan)}")
    starts = segment_start_frames(plan)
    return [starts[i] for i in range(1, len(plan)) if zooms[i] != zooms[i - 1]]


def finale_frame(plan):
    """بداية آخر مقطع — أو `None` لو ما في إلا مقطع واحد."""
    return segment_start_frames(plan)[-1] if len(plan) > 1 else None


def collect_events(plan, zooms=None, caption_frames=(), word_frames=(),
                   cfg=None):
    """
    كل الأحداث المرشَّحة، **قبل** التصفية. مرتّبة بـ`(إطار, أولوية)`.

    `caption_frames` و`word_frames` بتجي جاهزة من مسار الكابشن —
    هالوحدة ما بتحسبهن، عشان تضل نقية ومستقلة عن `captions.py`.
    """
    c = merged_config(cfg)
    ev = c["events"]
    total = sum(plan)
    out = []

    def add(frames, kind):
        if ev.get(kind, {}).get("enabled"):
            out.extend(Event(f, kind) for f in frames)

    add([0], "start")
    add(cut_frames(plan), "cut")
    add(zoom_change_frames(plan, zooms), "zoom")
    add(sorted(set(int(f) for f in caption_frames)), "caption")
    add(sorted(set(int(f) for f in word_frames)), "word")
    fin = finale_frame(plan)
    if fin is not None:
        add([fin], "finale")

    # برّا المدى = ما بينعرض أصلًا. الحذف هون أوضح من تمريره للرسم.
    out = [e for e in out if 0 <= e.frame < total]
    return sorted(out, key=_order)


def _order(e):
    return (e.frame, PRIORITY.index(e.kind))


# ---------------------------------------------------------- التصفية

def suppress(events, gap_frames):
    """
    مؤثر واحد لكل نافذة `gap_frames` — **الأعلى أولوية بالنافذة**.

    ### ليش نافذة وأولوية، مش "الأول بيفوز"

    "الأول بيفوز" بيعطي نتيجة عشوائية بحالتنا الفعلية. مقيس
    (`SFX-SPEC.md` §C.5): تغيّرات الزوم بتقع على **نفس** إطارات حدود
    المقاطع. لو الترتيب وحده هو الحكم، `zoom` اللي وقع قبل `cut`
    بإطار واحد بيبلع القطة — والقطة هي الحدث الأهم إيقاعيًا.

    فالقاعدة: قسّم لعناقيد عرض كل واحد `gap_frames`، وخُد من كل
    عنقود **الأقوى**؛ وعند التعادل **الأبكر**.

    ### ليش النافذة من أول عنصر مش سلسلة متصلة

    السلسلة (كل عنصر قريب من اللي قبله) ممكن تمتد بلا حدّ فتبلع
    كابشنات متتابعة كلها. النافذة الثابتة بتحدّ العرض بـ`gap_frames`
    مهما كانت الكثافة — سلوك متوقَّع وقابل للحساب.
    """
    if gap_frames <= 0:
        return sorted(events, key=_order)
    kept, i = [], 0
    ordered = sorted(events, key=_order)
    while i < len(ordered):
        anchor = ordered[i].frame
        j = i
        while j < len(ordered) and ordered[j].frame - anchor < gap_frames:
            j += 1
        cluster = ordered[i:j]
        kept.append(min(cluster, key=_order_by_priority))
        i = j
    return kept


def _order_by_priority(e):
    return (PRIORITY.index(e.kind), e.frame)


def limit_concurrent(cues, max_concurrent, durations):
    """
    ولا لحظة فيها أكتر من `max_concurrent` مؤثر شغّال.

    `durations` = `{اسم الأصل: طوله بالإطارات}`. **بلاها ما بينطبّق
    شي** — وهاد مكتوب مش مسكوت عنه: مدد الأصول بتيجي من قراءة الملفات،
    وهالوحدة نقية فما بتقرا ملفات.

    الأقوى بيبقى: منمشي بترتيب الأولوية ومنسقّط اللي بيتعدّى الحدّ.
    """
    if not durations or max_concurrent is None or max_concurrent <= 0:
        return list(cues)
    kept = []
    for cue in sorted(cues, key=_order_by_priority):
        end = cue.frame + int(durations.get(cue.asset, 0))
        overlapping = sum(
            1 for k in kept
            if k.frame < end and cue.frame < k.frame + int(durations.get(k.asset, 0)))
        if overlapping < max_concurrent:
            kept.append(cue)
    return sorted(kept, key=lambda c: (c.frame, PRIORITY.index(c.kind)))


# ------------------------------------------------------------- الخطة

def merged_config(cfg):
    """دمج ضحل مع الافتراضيات — الإعداد الناقص بياخد الافتراضي."""
    cfg = cfg or {}
    out = dict(DEFAULTS)
    out.update({k: v for k, v in cfg.items() if k != "events"})
    events = {k: dict(v) for k, v in DEFAULTS["events"].items()}
    for k, v in (cfg.get("events") or {}).items():
        events.setdefault(k, {}).update(v)
    out["events"] = events
    return out


def plan_cues(plan, fps, zooms=None, caption_frames=(), word_frames=(),
              cfg=None, sr=DEFAULT_SR, durations=None):
    """
    الخطة كاملة: أحداث -> تصفية -> مؤثرات بفهارس عيّنات.

    بترجّع `[Cue]` مرتّبة بالإطار. `Cue.sample` هو التمثيل الوحيد
    اللي بيوصل للرسم — الإطار محفوظ للقراءة والفحص بس.
    """
    c = merged_config(cfg)
    if not c.get("enabled", True):
        return []
    frame_to_sample(0, fps, sr)             # بتفشل بدري لو fps ما بتقسّم sr

    events = collect_events(plan, zooms, caption_frames, word_frames, cfg)
    events = suppress(events, seconds_to_frames(c["min_gap"], fps))

    cues = []
    for e in events:
        spec = c["events"][e.kind]
        cues.append(Cue(frame=e.frame,
                        sample=frame_to_sample(e.frame, fps, sr),
                        kind=e.kind, asset=spec["asset"],
                        gain=float(spec.get("gain", 0.25))))
    return limit_concurrent(cues, c.get("max_concurrent"), durations)


def asset_usage(cues):
    """`{اسم الأصل: عدد استعمالاته}` — مدخل `asplit` بمرحلة الرسم."""
    out = {}
    for c in cues:
        out[c.asset] = out.get(c.asset, 0) + 1
    return out


def assert_within(cues, total_frames):
    """
    حارس: ولا مؤثر برّا مدى المخرَج، ولا اتنين على نفس الإطار.

    التاني مهم لأن مؤثرين بنفس اللحظة بيجمعوا ذروتهن، وهاد أقرب
    طريق للقصّ رغم كل حساب الهامش.
    """
    seen = set()
    for c in cues:
        if not 0 <= c.frame < total_frames:
            raise ValueError(f"مؤثر برّا المدى: {c!r} (المجموع {total_frames})")
        if c.frame in seen:
            raise ValueError(f"مؤثران على نفس الإطار {c.frame}")
        seen.add(c.frame)
