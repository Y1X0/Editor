"""
C.1–C.5 — القياسات الباقية قبل التنفيذ (المرحلة ٠).
"""
import os, subprocess, sys, time, math
sys.path.insert(0, "/home/user/Editor"); sys.path.insert(0, "/home/user/Editor/tests")
import tools as T
SR = T.SR
A = "/home/user/Editor/assets/sfx"

print("═══ C.2 — كلفة قياس مستوى الكلام (volumedetect) ═══")
import pathlib
from measure import build_source
D = pathlib.Path("/tmp/sfx_p0"); D.mkdir(exist_ok=True)
src = build_source(D, width=320, height=568, fps=30, nframes=900)   # ٣٠ ثانية
t0 = time.time()
r = subprocess.run(["ffmpeg","-i",src["path"],"-map","0:a","-af","volumedetect",
                    "-f","null","-"], capture_output=True, text=True)
el = time.time()-t0
peak = [l for l in r.stderr.splitlines() if "max_volume" in l]
print(f"  مصدر ٣٠s · volumedetect: {el:.2f}s · {peak[0].split(']')[-1].strip() if peak else '?'}")
t0 = time.time()
subprocess.run(["ffmpeg","-i",src["path"],"-map","0:a","-c","copy","-f","null","-"],
               capture_output=True)
print(f"  للمقارنة، مرور بلا تحليل: {time.time()-t0:.2f}s")

print("\n═══ C.3 — أصل تالف أو بمدة صفر ═══")
open("/tmp/p0_empty.wav","wb").write(b"")
T.run(["-f","lavfi","-i",f"anullsrc=sample_rate={SR}:channel_layout=stereo",
       "-t","0.001","-c:a","pcm_s16le","/tmp/p0_tiny.wav"])
open("/tmp/p0_junk.wav","wb").write(b"RIFF____WAVEjunkjunk"*50)
T.silence("/tmp/p0_bed.wav", 2.0)
FMT=f"aformat=sample_rates={SR}:channel_layouts=stereo"
for p,lbl in (("/tmp/p0_empty.wav","ملف فاضي"),("/tmp/p0_tiny.wav","مدة ١ms"),
              ("/tmp/p0_junk.wav","بايتات زبالة")):
    try:
        T.run(["-i","/tmp/p0_bed.wav","-i",p,"-filter_complex",
               f"[1:a]{FMT},adelay={SR}S:all=1[s];[0:a]{FMT}[b];"
               f"[b][s]amix=inputs=2:duration=first:normalize=0[a]",
               "-map","[a]","-c:a","pcm_s16le","/tmp/p0_out.wav"])
        n=len(T.pcm("/tmp/p0_out.wav"))
        print(f"  {lbl:<16} ✅ نجح · طول {n} (مرجع {2*SR})"
              f"{'  ⚠️ الطول اختلف' if n!=2*SR else ''}")
    except RuntimeError as e:
        print(f"  {lbl:<16} ❌ فشل: {str(e).strip().splitlines()[-1][:70]}")

print("\n═══ C.5 — كم مؤثرًا لريل واقعي؟ ═══")
from autoreel import cuts as C, captions as CAP, graph as G
import json
cfg=json.load(open("/home/user/Editor/config.json"))
# ريل ٦٠s بإيقاع كلام واقعي: ~٢.٥ كلمة/ثانية
words=[{"word":f"w{i}","start":i*0.40,"end":i*0.40+0.32} for i in range(150)]
segs=C.segments_from_words(words,60.0,**cfg["cuts"])
plan=C.frame_plan(segs,30)
groups=CAP.group_words(C.remap_words(words,segs,durations=[n/30 for n in plan]),
                       cfg["captions"]["max_words"])
print(f"  ريل {sum(plan)/30:.1f}s · {len(segs)} مقطع · {len(groups)} كابشن")
zooms=G.zoom_values(cfg,len(plan))
zchg=sum(1 for i in range(1,len(zooms)) if zooms[i]!=zooms[i-1])
print(f"  أحداث محتملة: حدود مقاطع {len(segs)-1} · كابشنات {len(groups)} "
      f"· تغيّرات زوم {zchg} · بداية/نهاية 2")
tot=(len(segs)-1)+len(groups)+2
print(f"  المجموع بلا tick: **{tot}** مؤثر لريل ٦٠s")
print(f"  مع tick لكل كلمة: {tot+len(words)} — وهاد سبب إطفائه افتراضيًا")
