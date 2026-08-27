"""نقطة التشغيل: python -m autoreel.cli input.mp4 -o out.mp4"""
import argparse, json, os, tempfile, shutil, sys
from . import (transcribe as T, cuts as C, captions as CAP, render as R,
               exports as X)


def _one_export(name, cfg, src, segs, w2, out_path, work, a, multi):
    """
    تصدير مقاس واحد. بيرجّع سطر ملخّص.

    `w2` = الكلمات بعد `remap_words`، محسوبة **مرة وحدة** برّا الحلقة:
    دالة نقية من (words, segs) وما فيها ولا مدخل له علاقة بأبعاد
    المخرَج. حسابها لكل مقاس شغل ضايع، وأسوأ — بيفتح باب اختلاف
    التوقيتات بين المقاسات.

    الكابشن بينرسم من جديد بعرض هالمقاس — مش بينشتق بالقص من مقاس
    تاني، وإلا بيرجع باگ النص المقصوص من الباب الخلفي. `_fit` بتاخد
    العرض المتاح كمدخل أصلًا فإعادة الرسم شبه مجانية.
    """
    W, H = cfg["output"]["width"], cfg["output"]["height"]
    tag = f"[{name}]"

    caps = []
    if cfg["captions"]["enabled"] and not a.no_captions and w2:
        groups = CAP.group_words(w2, cfg["captions"]["max_words"])
        texts = [" ".join(g["words"]) for g in groups]
        # افحص قبل ما ترسم: أرخص من ترميز كامل بينطلع تالف.
        CAP.assert_fits_frame(texts, cfg["captions"], W, H, label=name)
        caps = CAP.build_caption_pngs(groups, cfg["captions"], W,
                                      os.path.join(work, f"caps_{name}"),
                                      bridge_gap=cfg["cuts"]["min_gap"])
        print(f"  {tag} {len(groups)} كابشن ({len(caps)} إطار)")

    fit = cfg.get("geometry", {}).get("fit", "crop")
    size = cfg["captions"]["size"]

    if a.preview_frames:
        # منتصف أول مقطع: بالمصدر للـseek، وبالتوقيت الجديد للكابشن.
        a0, b0 = segs[0]
        png = next((p for p, s, e in caps if s <= (b0 - a0) / 2 <= e), None)
        R.preview_frame(src, (a0 + b0) / 2, cfg, out_path, caption_png=png,
                        dry_run=a.dry_run)
        return (f"  {name:<8} {W}×{H}  fit={fit:<5} "
                f"crop_bias={cfg.get('geometry', {}).get('crop_bias', 0.5)}  {out_path}")

    base = R.build_base(src, segs, cfg, os.path.join(work, name),
                        dry_run=a.dry_run)
    R.burn_captions(base, caps, cfg, out_path,
                    workdir=os.path.join(work, name), dry_run=a.dry_run)

    mb = "" if a.dry_run else f" · {os.path.getsize(out_path)/1e6:.1f}MB"
    return f"  {name:<8} {W}×{H}  fit={fit:<5} خط={size}{mb}  {out_path}"


def main():
    ap = argparse.ArgumentParser(description="محرر ريلز أوتوماتيكي — قص وزوم وكابشن عربي")
    ap.add_argument("input")
    ap.add_argument("-o", "--output", default="out.mp4")
    ap.add_argument("-c", "--config", default="config.json")
    ap.add_argument("--srt", help="استخدم SRT جاهز بدل Whisper")
    ap.add_argument("--sizes", help="مقاسات التصدير: reel,square,wide أو all")
    ap.add_argument("--no-captions", action="store_true")
    ap.add_argument("--no-cut", action="store_true", help="لا تشيل الصمت")
    ap.add_argument("--no-motion", action="store_true")
    ap.add_argument("--keep", action="store_true", help="خلّي الملفات المؤقتة")
    ap.add_argument("--dry-run", action="store_true",
                    help="اطبع أوامر ffmpeg بدون ما تشغّلها")
    ap.add_argument("--preview-frames", action="store_true",
                    help="إطار PNG من كل مقاس ووقّف — قبل ما تصرف ترميز")
    a = ap.parse_args()

    root = json.load(open(a.config, encoding="utf-8"))
    if a.no_motion:
        root["motion"]["enabled"] = False

    picked = X.select(root, a.sizes)
    multi = len(picked) > 1

    want_caps = root["captions"]["enabled"] and not a.no_captions
    if want_caps:
        # افشل هلأ مش بعد ما القص والزوم ياكلوا دقايق ffmpeg. مشروط عمدًا:
        # بدون الشرط بينكسر --no-captions على بيئة بلا raqm.
        CAP._require_raqm()

    work = tempfile.mkdtemp(prefix="autoreel_")
    failed = []
    try:
        # ---- محسوب مرة وحدة: مستقل تمامًا عن مقاس المخرَج ----
        dur = C.probe_duration(a.input)
        print(f"[1/4] المدة الأصلية: {dur:.1f}s")

        # Whisper لازم للقص أو للكابشن. بدون الاتنين ما إله لزوم، وقبل
        # هيك كان بينزّل الموديل ويفرّغ بلا فايدة نهائيًا.
        need_words = (not a.no_cut) or want_caps
        if a.srt:
            words = T.from_srt(a.srt)
            print(f"[2/4] تفريغ: {len(words)} كلمة (من SRT)")
        elif need_words:
            words = T.transcribe(
                a.input, root["whisper_model"], root["language"],
                cache=T.cache_path(a.input, root["whisper_model"], root["language"]))
            print(f"[2/4] تفريغ: {len(words)} كلمة")
        else:
            words = []
            print("[2/4] تفريغ: تخطّي — لا قص ولا كابشن")

        if a.no_cut or not words:
            segs = [(0.0, dur)]
        else:
            segs = C.segments_from_words(words, dur, **root["cuts"])
        new_dur = C.total_after_cut(segs)
        print(f"[3/4] {len(segs)} مقطع · بعد القص {new_dur:.1f}s "
              f"(انشال {dur-new_dur:.1f}s)")

        # `min_seg` بتشيل المقاطع القصيرة وكلماتها. كان بيصير بصمت،
        # فكلمة قصيرة لحالها («تمام»، «أيوا») بتختفي من الريل بلا خبر.
        gone = C.dropped_words(words, segs, min_ratio=0.45) if words else []
        if gone:
            print(f"⚠️  {len(gone)} كلمة انشالت مع القص: "
                  f"{' · '.join(gone[:12])}{' …' if len(gone) > 12 else ''}\n"
                  f"    صغّر cuts.min_seg لو كنت بدك تبقيها.", file=sys.stderr)

        # التوقيتات بعد القص — دالة نقية من (words, segs)، فمشتركة بين
        # كل المقاسات. حسابها مرة بيضمن كمان إنها متطابقة بينهن.
        #
        # المدد من `frame_plan` مش من `b-a`: ffmpeg بيرمّز عدد إطارات
        # مش زمنًا، فالتوقيت المبني على `b-a` بينزاح عن الصورة بمقدار
        # بيتراكم مع كل مقطع. `output.fps` مشترك ودهسه بتصدير مرفوض.
        fps = root["output"]["fps"]
        durations = [n / fps for n in C.frame_plan(segs, fps)]
        w2 = C.remap_words(words, segs, durations=durations) if words else []
        new_dur = sum(durations)

        # ---- لكل مقاس: كابشن جديد + ترميز ----
        what = "معاينة" if a.preview_frames else "تصدير"
        print(f"[4/4] {what} {len(picked)} مقاس: {', '.join(picked)}")
        rows = []
        for name in picked:
            cfg = X.resolve(root, name)
            out_path = (X.preview_path(a.output, name, multi) if a.preview_frames
                        else X.output_path(a.output, name, multi))
            d = os.path.dirname(os.path.abspath(out_path))
            os.makedirs(d, exist_ok=True)
            os.makedirs(os.path.join(work, name), exist_ok=True)
            try:
                rows.append(_one_export(name, cfg, a.input, segs, w2,
                                        out_path, work, a, multi))
            except Exception as e:
                # فشل مقاس ما بيوقف الباقي — بس كود الخروج بيصير ≠ ٠.
                failed.append(name)
                print(f"  ❌ [{name}] {e}", file=sys.stderr)

        if a.dry_run:
            head = "🔍 تجربة جافة — ما انكتب ولا ملف"
        elif a.preview_frames:
            head = "🖼️  إطارات معاينة — ما انعمل ترميز"
        else:
            head = "✅ خلص"
        print(f"\n{head}  ({new_dur:.1f}s)")
        for r in rows:
            print(r)
        if a.preview_frames and not a.dry_run:
            print("\n    شوف الإطارات وعدّل geometry.crop_bias إذا الوجه مقصوص،"
                  "\n    بعدين شغّل بدون --preview-frames.")
        if failed:
            print(f"\n❌ فشل: {', '.join(failed)}", file=sys.stderr)
    finally:
        if a.keep:
            print("temp:", work)
        else:
            shutil.rmtree(work, ignore_errors=True)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
