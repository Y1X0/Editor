"""نقطة التشغيل: python -m autoreel.cli input.mp4 -o out.mp4"""
import argparse, json, os, tempfile, shutil, sys
from . import transcribe as T, cuts as C, captions as CAP, render as R


def main():
    ap = argparse.ArgumentParser(description="محرر ريلز أوتوماتيكي — قص وزوم وكابشن عربي")
    ap.add_argument("input")
    ap.add_argument("-o", "--output", default="out.mp4")
    ap.add_argument("-c", "--config", default="config.json")
    ap.add_argument("--srt", help="استخدم SRT جاهز بدل Whisper")
    ap.add_argument("--no-captions", action="store_true")
    ap.add_argument("--no-cut", action="store_true", help="لا تشيل الصمت")
    ap.add_argument("--no-motion", action="store_true")
    ap.add_argument("--keep", action="store_true", help="خلّي الملفات المؤقتة")
    a = ap.parse_args()

    cfg = json.load(open(a.config, encoding="utf-8"))
    if a.no_motion:
        cfg["motion"]["enabled"] = False

    work = tempfile.mkdtemp(prefix="autoreel_")
    try:
        dur = C.probe_duration(a.input)
        print(f"[1/5] المدة الأصلية: {dur:.1f}s")

        if a.srt:
            words = T.from_srt(a.srt)
        else:
            words = T.transcribe(a.input, cfg["whisper_model"], cfg["language"],
                                 cache=os.path.splitext(a.input)[0] + ".words.json")
        print(f"[2/5] تفريغ: {len(words)} كلمة")

        if a.no_cut or not words:
            segs = [(0.0, dur)]
        else:
            segs = C.segments_from_words(words, dur, **cfg["cuts"])
        new_dur = C.total_after_cut(segs)
        print(f"[3/5] {len(segs)} مقطع · بعد القص {new_dur:.1f}s "
              f"(انشال {dur-new_dur:.1f}s)")

        base = R.build_base(a.input, segs, cfg, work)
        print("[4/5] القص والزوم خلصوا")

        caps = []
        if cfg["captions"]["enabled"] and not a.no_captions and words:
            w2 = C.remap_words(words, segs)
            groups = CAP.group_words(w2, cfg["captions"]["max_words"])
            caps = CAP.build_caption_pngs(groups, cfg["captions"],
                                          cfg["output"]["width"],
                                          os.path.join(work, "caps"))
            print(f"[5/5] {len(groups)} كابشن ({len(caps)} إطار)")

        R.burn_captions(base, caps, cfg, a.output)
        print(f"\n✅ {a.output}  ({new_dur:.1f}s)")
    finally:
        if a.keep:
            print("temp:", work)
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
