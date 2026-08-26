# auto-reel

محرر ريلز أوتوماتيكي بالعربي: قص الصمت + زوم عند القطات + كابشن عربي محروق
مع تلوين كاريوكي. مبني على ffmpeg + Pillow + faster-whisper.

## التنصيب (Termux)

```bash
pkg install python ffmpeg libraqm harfbuzz fribidi
pip install --no-binary :all: --force-reinstall Pillow
pip install -r requirements.txt
python -c "from PIL import features; print('raqm:', features.check('raqm'))"   # لازم True
```

## التنصيب (لينكس / ماك)

```bash
pip install -r requirements.txt
python -c "from PIL import features; print('raqm:', features.check('raqm'))"
```

## الاستخدام

```bash
python -m autoreel.cli raw.mp4 -o reel.mp4
python -m autoreel.cli raw.mp4 --srt subs.srt -o reel.mp4    # بدون Whisper
python -m autoreel.cli raw.mp4 --no-cut --no-motion -o reel.mp4
```

أول تشغيل بينزّل موديل Whisper (~٥٠٠MB للـ small). التفريغ بينحفظ بملف
`raw.words.json` جنب الفيديو، فالتشغيلات الجاية أسرع بكتير.

## المخرجات

1080×1920 · H.264 · الصوت مقصوص مع الصورة بنفس التوقيت.

## ملاحظة

كل التفاصيل التقنية والمطبّات موثّقة بـ`CLAUDE.md` — اقرأه قبل ما تعدّل
على الكابشن.
