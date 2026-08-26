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
python -m autoreel.cli raw.mp4 --sizes all -o reel.mp4        # ريلز + مربع + عريض
python -m autoreel.cli raw.mp4 --sizes all --preview-frames -o reel.mp4
python -m autoreel.cli raw.mp4 --dry-run -o reel.mp4          # اطبع أوامر ffmpeg بس
```

على فيديو جديد شغّل `--preview-frames` أول شي: بيطلّع إطار PNG من كل
مقاس بلا ترميز، فتشوف نافذة القص قبل ما تصرف دقايق. لو الوجه مقصوص
بالمربع، عدّل `geometry.crop_bias` (أصغر = النافذة بتطلع لفوق).

أول تشغيل بينزّل موديل Whisper (~٥٠٠MB للـ small). التفريغ بينحفظ بملف
`raw.small.ar.words.json` جنب الفيديو — الموديل واللغة جزء من الاسم،
فتغييرهن بالconfig بيفرّغ من جديد بدل ما يرجّع نتيجة قديمة.

## المخرجات

`reel` 1080×1920 · `square` 1080×1080 · `wide` 1920×1080 · H.264 · الصوت مقصوص مع الصورة بنفس التوقيت.

## الاختبارات

```bash
pip install -r requirements-dev.txt
pytest
pytest -m "not golden"    # لو مكدّس الخطوط عندك مختلف
```

## ملاحظة

كل التفاصيل التقنية والمطبّات موثّقة بـ`CLAUDE.md` — اقرأه قبل ما تعدّل
على الكابشن.
