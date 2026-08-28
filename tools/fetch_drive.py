#!/usr/bin/env python3
"""
تنزيل ملف عام من Google Drive — **أداة، مش كود إنتاج**.

ليش موجودة: اللقطات الحقيقية على درايف ومشارَكة `anyone with the link`،
ورفعها يدويًا كأصل release خطوة زايدة بتتكرّر كل مرة. المشغّل عنده
شبكة مفتوحة، فبينزّلها لحاله.

    python tools/fetch_drive.py <FILE_ID|رابط> -o footage/

درايف بيرجّع البايتات مباشرة للملفات الصغيرة، وصفحة تأكيد HTML للكبيرة
(تحذير فحص الفيروسات). التعامل مع الاتنين هون، **وبتحقّق إن اللي نزل
مش HTML** — بدون هالفحص بينحفظ ملف ٢ ك.ب اسمه `.MOV` وffmpeg بيفشل
برسالة ما إلها علاقة بالسبب.
"""
import argparse
import os
import re
import sys
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (autoreel fetch_drive)"
BASE = "https://drive.usercontent.google.com/download"


def file_id(s):
    """بيقبل معرّفًا خامًا أو أي شكل من روابط درايف."""
    m = (re.search(r"/file/d/([A-Za-z0-9_-]{20,})", s)
         or re.search(r"[?&]id=([A-Za-z0-9_-]{20,})", s))
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{20,}", s):
        return s
    raise SystemExit(f"ما قدرت أطلع معرّف الملف من: {s!r}")


def _open(url, opener):
    return opener.open(urllib.request.Request(url, headers={"User-Agent": UA}))


def fetch(fid, outdir, opener=None, chunk=1 << 20):
    """بينزّل ويرجّع المسار. بيرمي لو اللي نزل صفحة HTML مش ملفًا."""
    opener = opener or urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor())
    url = f"{BASE}?id={fid}&export=download&confirm=t"
    r = _open(url, opener)
    ctype = r.headers.get("Content-Type", "")

    if "text/html" in ctype:
        # صفحة تأكيد للملفات الكبيرة: فيها نموذج بحقول مخفية.
        html = r.read().decode("utf-8", "replace")
        fields = dict(re.findall(
            r'name="([^"]+)"\s+value="([^"]*)"', html))
        if not fields.get("id"):
            raise SystemExit(
                "درايف رجّع HTML بلا نموذج تنزيل — غالبًا الملف مش عام. "
                "خلّي المشاركة «anyone with the link» وجرّب كمان مرة.")
        r = _open(f"{BASE}?{urllib.parse.urlencode(fields)}", opener)
        ctype = r.headers.get("Content-Type", "")
        if "text/html" in ctype:
            raise SystemExit("درايف ضلّ يرجّع HTML بعد التأكيد.")

    name = "download"
    cd = r.headers.get("Content-Disposition", "")
    m = re.search(r"filename\*=UTF-8''([^;]+)", cd) or \
        re.search(r'filename="([^"]+)"', cd)
    if m:
        name = urllib.parse.unquote(m.group(1))
    # اسم الملف جاي من الشبكة — خدّ الاسم الأساسي وبس.
    name = os.path.basename(name.replace("\\", "/")) or "download"

    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, name)
    n = 0
    with open(path, "wb") as f:
        while True:
            b = r.read(chunk)
            if not b:
                break
            f.write(b)
            n += len(b)

    # الفشل بصوت: ملف صغير جدًا يعني صفحة خطأ انحفظت باسم فيديو.
    if n < 4096:
        head = open(path, "rb").read(200)
        raise SystemExit(f"اللي نزل {n} بايت وبيبدأ بـ{head[:80]!r} — "
                         f"مش ملف فيديو.")
    # المسار على stdout **لحاله** عشان ينلتقط بسكربت؛ الباقي على stderr.
    print(f"نزل {n/1e6:.1f} MB -> {path}", file=sys.stderr)
    print(path)
    return path


def main():
    ap = argparse.ArgumentParser(description="نزّل ملفًا عامًا من درايف")
    ap.add_argument("id_or_url")
    ap.add_argument("-o", "--outdir", default="footage")
    a = ap.parse_args()
    fetch(file_id(a.id_or_url), a.outdir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
