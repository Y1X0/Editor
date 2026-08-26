"""أدوات مشتركة للاختبارات."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

GOLDEN = Path(__file__).parent / "golden"


def _raqm():
    try:
        from PIL import features
        return features.check("raqm")
    except Exception:
        return False


HAS_RAQM = _raqm()
needs_raqm = pytest.mark.skipif(
    not HAS_RAQM, reason="Pillow بدون raqm — رسم الكابشن العربي ما بينفحص")


@pytest.fixture
def cfg():
    """الconfig الحقيقي، بس بمسار خط مطلق حتى تشتغل من أي مجلد."""
    c = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    c["captions"]["font"] = str(ROOT / c["captions"]["font"])
    return c


@pytest.fixture
def caps(cfg):
    return cfg["captions"]


@pytest.fixture(autouse=True)
def _clear_caches():
    """كاش الملاءمة عالمي — لا تخلّي اختبار يلوّث اللي بعده."""
    try:
        from autoreel import captions as CAP
        CAP._FIT_CACHE.clear()
    except Exception:
        pass
    yield


def words(*triples):
    """اختصار: words(("هاد", 0.0, 0.4), ...) -> شكل الكلمات المعتمد."""
    return [{"word": w, "start": s, "end": e} for w, s, e in triples]


def text_bbox(img):
    """bbox الحبر داخل الصورة (بيفترض الصندوق شفاف)."""
    return img.split()[-1].getbbox()
