"""
S4 — القصّ (clipping) مع `normalize=0`، ومطابقة الصيغة.

`normalize=0` بتحفظ الكلام بالضبط — بس بتجمع، فالمجموع ممكن يتعدّى
١.٠ ويتقصّ. وSFX الجاهزة غالبًا 44.1k ستيريو، والمسار 48k.
"""
import tools as T
SR = T.SR


def loud(path, freq, dur, amp):
    T.run(["-f", "lavfi", "-i",
           f"sine=frequency={freq}:sample_rate={SR}:duration={dur}",
           "-af", f"volume={amp}", "-c:a", "pcm_s16le", path])
    return path


print("═══ القصّ عند التراكب ═══")
sp = loud("/tmp/l_sp.wav", 300, 3, 8.0)     # كلام عالي
print(f"  مستوى الكلام: {max(map(abs,T.pcm(sp))):.4f}")
for amp, lbl in ((1.0, "SFX هادئ"), (4.0, "SFX متوسط"), (8.0, "SFX عالي")):
    sfx = loud("/tmp/l_sfx.wav", 2000, 0.2, amp)
    T.run(["-i", sp, "-i", sfx, "-filter_complex",
           f"[1:a]adelay={SR}S[s];[0:a][s]amix=inputs=2:duration=first:normalize=0[a]",
           "-map", "[a]", "-c:a", "pcm_s16le", "/tmp/l_out.wav"])
    o = T.pcm("/tmp/l_out.wav")
    clip = sum(1 for v in o if abs(v) >= 0.999)
    print(f"  {lbl:<12} قمة SFX {max(map(abs,T.pcm(sfx))):.3f} -> "
          f"قمة المزيج {max(map(abs,o)):.4f} · عيّنات مقصوصة {clip}")

print("\n═══ عدم تطابق معدّل العيّنة والقنوات ═══")
# SFX بـ44.1k ستيريو — الشكل الشائع للأصول الجاهزة
T.run(["-f", "lavfi", "-i", "sine=frequency=2000:sample_rate=44100:duration=0.2",
       "-ac", "2", "-c:a", "pcm_s16le", "/tmp/m_sfx.wav"])
print("  SFX: 44100 Hz ستيريو | المسار: 48000 Hz")

for lbl, chain in (
    ("بلا aresample (خام)",
     f"[1:a]adelay={SR}S[s];[0:a][s]amix=inputs=2:duration=first:normalize=0[a]"),
    ("مع aresample+pan لمونو",
     f"[1:a]aresample={SR},pan=mono|c0=0.5*c0+0.5*c1,adelay={SR}S[s];"
     f"[0:a][s]amix=inputs=2:duration=first:normalize=0[a]"),
):
    try:
        T.run(["-i", sp, "-i", "/tmp/m_sfx.wav", "-filter_complex", chain,
               "-map", "[a]", "-c:a", "pcm_s16le", "/tmp/m_out.wav"])
        o = T.pcm("/tmp/m_out.wav")
        imp = T.impulses(o)
        floor = T.impulses(T.pcm("/tmp/m_sfx.wav"))[0]
        pos = [i - floor for i in imp if i > SR // 2]
        print(f"  {lbl:<26} ✅ طول {len(o)} · موقع المؤثر "
              f"{pos[0] if pos else '?'} (المطلوب {SR}) "
              f"خطأ {pos[0]-SR if pos else '?'}")
    except RuntimeError as e:
        print(f"  {lbl:<26} ❌ {str(e).strip().splitlines()[-1][:90]}")
