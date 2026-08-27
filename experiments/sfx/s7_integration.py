"""
S7 — دمج فعلي بالمسار الحقيقي: هل E1/E2 بيصمدوا؟

نقطة الإدخال المقترحة: بعد `concat` وقبل `asplit=M`. المؤثرات مستقلة
عن المقاس زي الصوت بالضبط، فمكانها قبل التوزيع مش بعده.

    [0:a] aresample,asplit=K -> atrim(عيّنة) -> concat -> [acat]
    [acat] + مؤثرات  --amix normalize=0-->  [amixed] -> asplit=M
"""
import os, sys, json, subprocess
sys.path.insert(0, "/home/user/Editor")
sys.path.insert(0, "/home/user/Editor/tests")
import tools as T
from autoreel import graph as G, cuts as C
from measure import build_source, count_frames
from measure.clicks import click_times
import pathlib

SR, FPS = 48000, 30
D = pathlib.Path("/tmp/sfx_e2e"); D.mkdir(exist_ok=True)
src = build_source(D, width=320, height=568, fps=FPS, nframes=420)
T.click(str(D / "click.wav"), dur=0.03, freq=3000)

segs = [(1.0, 3.0), (5.0, 7.5), (9.0, 11.0), (12.5, 14.0)]
plan = C.frame_plan(segs, FPS)
starts = G.start_frames(segs, FPS)
TOTAL = sum(plan)
print(f"خطة الإطارات {plan} = {TOTAL} إطار = {TOTAL/FPS:.3f}s\n")

# مؤثرات على إطارات مخرَج محدَّدة — الفهرس هو الزمن، زي الكابشن
SFX_FRAMES = [0, 17, 44, 60, 91, 120, 150, 180]
SPF = SR // FPS


def build(with_sfx):
    parts = [G.video_stem(FPS, starts, plan), G.split_chain("stem", ["z0"])]
    parts += G.audio_chain(FPS, starts, plan, ["acat_out"], sr=SR)
    g = "; ".join(parts)
    # audio_chain بتنهي بـ[acat]anull[acat_out] — منركّب فوقها
    if with_sfx:
        n = len(SFX_FRAMES)
        fx = [f"[1:a]aformat=sample_rates={SR}:channel_layouts=stereo,asplit={n}"
              + "".join(f"[c{i}]" for i in range(n))]
        for i, fr in enumerate(SFX_FRAMES):
            fx.append(f"[c{i}]adelay={fr*SPF}S:all=1[s{i}]")
        fx.append("[acat_out]" + "".join(f"[s{i}]" for i in range(n))
                  + f"amix=inputs={n+1}:duration=first:normalize=0[amixed]")
        g += "; " + "; ".join(fx)
        alabel = "amixed"
    else:
        alabel = "acat_out"
    parts2 = [G.size_chain({"output": {"width": 320, "height": 568, "fps": FPS},
                            "motion": {"enabled": False, "zoom_cycle": [1.0],
                                       "pan_px": 0},
                            "geometry": {"fit": "crop", "crop_bias": 0.5}},
                           plan, [1.0] * len(plan), "z0", "g0", 320, 568)]
    g += "; " + "; ".join(parts2)
    return g, alabel


for with_sfx in (False, True):
    g, alabel = build(with_sfx)
    gp = str(D / "g.txt"); open(gp, "w").write(g)
    out = str(D / ("with.mp4" if with_sfx else "without.mp4"))
    ins = ["-i", src["path"]]
    if with_sfx:
        ins += ["-i", str(D / "click.wav")]
    T.run(ins + ["-filter_complex_script", gp, "-map", "[g0]", "-map", f"[{alabel}]",
                 "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
                 "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                 "-ar", str(SR), "-ac", "2", out])
    frames = count_frames(out)
    samples = len(T.pcm(out))
    lbl = "مع مؤثرات" if with_sfx else "بلا مؤثرات"
    print(f"{lbl:<12} إطارات {frames} (مطلوب {TOTAL}) "
          f"{'✅' if frames == TOTAL else '❌'} · عيّنات {samples}")

# انزياح نقرات المصدر (E2) — نفس الحارس الحالي
print("\n--- E2: نقرات المصدر (الكلام) ---")
for name in ("without", "with"):
    ct = click_times(str(D / f"{name}.mp4"))
    exp = []
    off = 0
    for (a, b), n in zip(segs, plan):
        first = -(-(a * SR) // (SR // FPS))
        exp.append(off)
        off += n / FPS
    print(f"  {name:<8} عدد النقرات المكتشفة: {len(ct)}  أوّلها {ct[:4]}")
