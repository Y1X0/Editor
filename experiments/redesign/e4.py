"""وين بالضبط بينضيع معدّل الإطارات؟ (ليش cfr الافتراضي بيعيد التشكيل لـ25)"""
import subprocess, re

SRC = "counter.mp4"


def sh(a):
    return subprocess.run(a, capture_output=True, text=True)


def probe(graph, label):
    """نرمّز 2 ثانية ونشوف شو معدّل الإطارات اللي اختاره ffmpeg للمخرَج."""
    r = sh(['ffmpeg', '-y', '-loglevel', 'info', '-i', SRC, '-filter_complex', graph,
            '-map', '[out]', '-c:v', 'libx264', '-preset', 'ultrafast',
            '-pix_fmt', 'yuv420p', '/tmp/e4.mp4'])
    m = re.findall(r'Stream #0:0.*?,\s*([\d.]+)\s*fps', r.stderr)
    n = re.findall(r'frame=\s*(\d+)',
                   sh(['ffmpeg', '-i', '/tmp/e4.mp4', '-f', 'null', '-']).stderr)
    print(f"{label:46s} fps المخرَج={m[-1] if m else '?':>5s}  إطارات={n[-1] if n else '?'}")


# المصدر ٦٠٠ إطار / ٢٠ ثانية / ٣٠fps
probe("[0:v]null[out]", "null (بلا شي)")
probe("[0:v]setpts=PTS-STARTPTS[out]", "setpts لحاله")
probe("[0:v]trim=start=0:end=2[out]", "trim لحاله (2s -> المتوقع 60)")
probe("[0:v]trim=start=0:end=2,setpts=PTS-STARTPTS[out]", "trim+setpts (المتوقع 60)")
probe("[0:v]trim=start=0:end=2,setpts=PTS-STARTPTS,fps=30[out]", "trim+setpts+fps=30")
probe("[0:v]scale=320:240[out]", "scale لحاله")
probe("[0:v]split=2[a][b];[a][b]concat=n=2:v=1:a=0[out]", "concat لحاله (المتوقع 1200)")
