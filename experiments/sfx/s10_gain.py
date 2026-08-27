"""
S10 — تثبيت مستوى الكلام عند الهدف مهما كان شكل المصدر.

المشكلة المقاسة: `volume=0.70` على `[acat]` مونو بتوصل **٠.٤٩٥**،
لأن التحويل مونو->ستيريو بـlibswresample بيحفظ **الطاقة** (١/√٢ لكل
قناة) مش السعة. مصدر ستيريو ما بيمرق بالتحويل فبيوصل ٠.٧٠.

المطلوب: طريقة **صحيحة بffmpeg** توصل ٠.٧٠ بالحالتين — مش تعويضًا
أعمى بضرب ١.٤١٤.
"""
import tools as T
SR = T.SR
FMT = f"aformat=sample_rates={SR}:channel_layouts=stereo"
TARGET = 0.70

def src(ch, amp=8):
    p = f"/tmp/s10_{ch}.wav"
    T.run(["-f","lavfi","-i",f"sine=frequency=300:sample_rate={SR}:duration=1",
           "-af",f"volume={amp}","-ac",str(ch),"-c:a","pcm_s16le",p])
    return p, max(map(abs,T.pcm(p)))

# مؤثر ستيريو بيفرض على المزيج شكلًا ستيريو — نفس وضع الإنتاج
T.run(["-f","lavfi","-i",f"sine=frequency=3000:sample_rate={SR}:duration=0.05",
       "-ac","2","-c:a","pcm_s16le","/tmp/s10_sfx.wav"])

CANDIDATES = {
    "أ. volume وحده (الحالي)":
        f"volume={TARGET}",
    "ب. aformat ثم volume":
        f"{FMT},volume={TARGET}",
    "ج. aresample rematrix_volume=1":
        f"aresample={SR}:rematrix_volume=1,{FMT},volume={TARGET}",
    "د. pan صريح (تكرار القناة)":
        f"pan=stereo|c0=c0|c1=c0,volume={TARGET}",
}

print(f"الهدف: مستوى الكلام بالمخرَج = {TARGET} × ذروة المصدر\n")
print(f"{'الطريقة':<34} {'مونو':>18} {'ستيريو':>18}")
for label, chain in CANDIDATES.items():
    row = []
    for ch in (1, 2):
        p, base = src(ch)
        try:
            T.run(["-i",p,"-i","/tmp/s10_sfx.wav","-filter_complex",
                   f"[0:a]{chain}[spk];[1:a]{FMT},volume=0.25,adelay=40000S:all=1[s];"
                   f"[spk][s]amix=inputs=2:duration=first:normalize=0[a]",
                   "-map","[a]","-c:a","pcm_s16le","/tmp/s10_out.wav"])
            got = max(map(abs, T.pcm("/tmp/s10_out.wav")[:30000]))   # قبل المؤثر
            row.append(f"{got/base:.4f}")
        except RuntimeError as e:
            row.append("فشل")
    print(f"{label:<34} {row[0]:>18} {row[1]:>18}")
