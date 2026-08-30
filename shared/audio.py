"""طبقة الصوت — تخطيط المؤثرات ومزج الموسيقى.

كل اللي هون موجود بـ`autoreel.sfx` و`autoreel.graph` ومعايَر ومفحوص
هناك. مجموع هون عشان يكون واضحًا شو بينشارك، ولأن `ai_pipeline`
ممنوعة تستورد `autoreel` مباشرة.

**ولا سطر منطق** — إعادة تصدير بالكامل، زي باقي `shared/`.

والقيم اللي بتيجي معهن **مقيسة، لا مختارة بالذوق** (`SFX-SPEC.md`):

    speech_gain 0.70        كسب الكلام تحت المؤثرات
    music_gain  0.12        كسب الموسيقى تحت الكلام
    الهامش: 0.70 + 0.90 × 0.25 = 0.925 < 1.0  ← ولا عيّنة مقصوصة

وتلات قواعد ما بتتغيّر، وكلها مخبوزة بالسلاسل اللي بينتصدّروا هون:
`normalize=0` إلزامية بـ`amix` · `all=1` و`aformat` **قبل** `adelay`
· ولا `alimiter` (بيأخّر التيار ٢٣٩ عيّنة).
"""
from autoreel.graph import (                      # noqa: F401
    DEFAULT_MUSIC_FADE,
    DEFAULT_MUSIC_GAIN,
    DEFAULT_MUSIC_SPEECH_GAIN,
    DEFAULT_SPEECH_GAIN,
    music_chain,
    sfx_chain,
)
from autoreel.render import sfx_asset             # noqa: F401
from autoreel.sfx import (                        # noqa: F401
    PRIORITY,
    asset_usage,
    assert_within,
    merged_config,
    plan_cues,
)

__all__ = [
    "plan_cues", "asset_usage", "assert_within", "merged_config", "PRIORITY",
    "sfx_chain", "music_chain", "sfx_asset",
    "DEFAULT_SPEECH_GAIN", "DEFAULT_MUSIC_GAIN",
    "DEFAULT_MUSIC_SPEECH_GAIN", "DEFAULT_MUSIC_FADE",
]
