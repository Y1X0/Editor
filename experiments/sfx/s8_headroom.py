"""
S8 — التعامل مع القصّ: `alimiter` مقابل تخفيض الكسب.

`normalize=0` بتجمع، فمصدر عالي + مؤثر = قصّ. السؤال الحاسم:
هل `alimiter` بيلمس الكلام لما ما يكون في قصّ أصلًا؟ لأنه لو بيلمسه،
بنكون كسرنا خاصية "الكلام محفوظ عيّنة بعيّنة" اللي بتحمي E2.
"""
import tools as T
SR = T.SR

def tone(path, freq, dur, amp):
    T.run(["-f","lavfi","-i",f"sine=frequency={freq}:sample_rate={SR}:duration={dur}",
           "-af",f"volume={amp}","-ac","2","-c:a","pcm_s16le",path]); return path

CLICK = tone("/tmp/h_click.wav", 3000, 0.05, 1.0)
FMT = f"aformat=sample_rates={SR}:channel_layouts=stereo"

def render(speech_amp, sfx_gain, tail):
    sp = tone("/tmp/h_sp.wav", 300, 3.0, speech_amp)
    fc = (f"[1:a]{FMT},volume={sfx_gain},adelay={SR}S:all=1[s];"
          f"[0:a]{FMT}[b];[b][s]amix=inputs=2:duration=first:normalize=0[m];"
          f"[m]{tail}[a]")
    T.run(["-i",sp,"-i",CLICK,"-filter_complex",fc,"-map","[a]",
           "-c:a","pcm_s16le","/tmp/h_out.wav"])
    return T.pcm(sp), T.pcm("/tmp/h_out.wav")

print(f"{'كلام':>6} {'SFX':>6} {'الذيل':<26} {'قمة':>7} {'مقصوص':>7} "
      f"{'تغيّر الكلام النظيف':>20}")
CLEAN = list(range(0, int(SR*0.9))) + list(range(int(SR*1.3), int(SR*2.9)))
for sp_amp in (0.5, 0.9):
    for gain, tail, lbl in (
        (1.0, "anull", "بلا شي"),
        (0.5, "anull", "SFX ‎-6dB"),
        (1.0, "alimiter=limit=0.98", "alimiter"),
        (1.0, "alimiter=limit=0.98:level=disabled", "alimiter level=disabled"),
    ):
        ref, out = render(sp_amp, gain, tail)
        n = min(len(ref), len(out))
        clip = sum(1 for v in out if abs(v) >= 0.999)
        worst = max(abs(out[i]-ref[i]) for i in CLEAN if i < n)
        print(f"{sp_amp:>6} {gain:>6} {lbl:<26} {max(map(abs,out)):>7.4f} "
              f"{clip:>7} {worst:>20.6f}")
    print()
