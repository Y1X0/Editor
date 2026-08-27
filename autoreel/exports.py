"""
حلّ إعدادات التصدير: كل مقاس بيرث من جذر الconfig ويدهس اللي بده إياه.

الهدف إن الإعداد ما ينتسخ مرة لكل مقاس. قسم `exports` بيسرد الفروقات
بس، والباقي بيورَث. القواعد مقصودة تكون مملّة ومتوقّعة — شوف CLAUDE.md
"""
import copy

# مشتركة بين كل المقاسات: خطة القص والحركة بتنحسبوا مرة وحدة، فدهسهن
# بتصدير بيوهم إنه إله أثر وهو ما إله.
SHARED = ("cuts", "motion")

# مفاتيح مشتركة داخل أقسام قابلة للدهس. `output.fps` بيحدّد شبكة
# الإطارات اللي بينبني عليها توقيت الكابشن (`cuts.frame_plan`)،
# وهو محسوب **مرة وحدة** لكل المقاسات. دهسه بتصدير بيخلي توقيت هداك
# المقاس مبنيًا على شبكة تانية بلا ما يحس حدا.
SHARED_KEYS = {"output": ("fps",)}


def names(cfg):
    """أسماء التصديرات المعرَّفة، بترتيب الconfig."""
    return list((cfg.get("exports") or {}).keys())


def resolve(cfg, name):
    """
    يرجّع config كامل ومستقل لتصدير واحد.

    الدمج عميق بمستوى واحد: كل قسم بينضم مفتاح بمفتاح، والمفتاح
    المسكوت عنه بيرث من الجذر. القيم المفردة بتنداهس كليًا —
    `zoom_cycle` بتنبدل ما بتندمج.

    الناتج نسخة عميقة، فالجذر ما بينتغيّر بين المقاسات. هاد تحديدًا
    اللي بينتج باگات «الإعداد تسرّب من المقاس اللي قبله».
    """
    exports = cfg.get("exports") or {}
    if name not in exports:
        avail = ", ".join(exports) or "(ولا واحد)"
        raise KeyError(f"تصدير مش معرّف: {name!r} — المتاح: {avail}")

    out = copy.deepcopy(cfg)
    out.pop("exports", None)

    for section, over in (exports[name] or {}).items():
        if section in SHARED:
            raise ValueError(
                f"التصدير {name!r} بيدهس {section!r}، وهاد مشترك بين كل "
                f"المقاسات — عدّله بجذر الconfig")
        if section not in cfg:
            raise KeyError(
                f"التصدير {name!r} بيدهس قسم مش موجود بالجذر: {section!r}")
        for k in SHARED_KEYS.get(section, ()):
            if isinstance(over, dict) and k in over:
                raise ValueError(
                    f"التصدير {name!r} بيدهس {section}.{k!r}، وهاد بيحدّد "
                    f"توقيت الكابشن لكل المقاسات — عدّله بجذر الconfig")
        if isinstance(over, dict) and isinstance(out.get(section), dict):
            out[section].update(copy.deepcopy(over))
        else:
            out[section] = copy.deepcopy(over)
    return out


def select(cfg, spec):
    """
    يحوّل نص `--sizes` لقائمة أسماء.

    None -> التصدير الافتراضي وحده (سلوك اليوم بالضبط).
    "all" -> كل المعرَّف بالconfig، بترتيبه.
    """
    if spec is None:
        return [names(cfg)[0]] if names(cfg) else []
    if spec.strip() == "all":
        return names(cfg)
    picked = [s.strip() for s in spec.split(",") if s.strip()]
    if not picked:
        raise ValueError("--sizes فاضي")
    for p in picked:
        if p not in names(cfg):
            avail = ", ".join(names(cfg)) or "(ولا واحد)"
            raise KeyError(f"مقاس مش معرّف: {p!r} — المتاح: {avail}")
    seen, uniq = set(), []
    for p in picked:                       # كرّرت اسم؟ مرة وحدة بتكفي
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def output_path(base_out, name, multi):
    """
    مقاس واحد = الاسم زي ما كتبه المستخدم، متوافق مع اليوم.
    أكتر من واحد = لاحقة لكلهم — مش «واحد بلا لاحقة والباقي بلاحقة».
    """
    import os
    if not multi:
        return base_out
    root, ext = os.path.splitext(base_out)
    return f"{root}.{name}{ext or '.mp4'}"


def preview_path(base_out, name, multi):
    """مسار إطار المعاينة — نفس قاعدة التسمية بس بامتداد png."""
    import os
    root, _ = os.path.splitext(output_path(base_out, name, multi))
    return root + ".preview.png"
