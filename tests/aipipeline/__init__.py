"""اختبارات `ai_pipeline`.

المجلّد **حزمة** (فيه `__init__.py`) بقصد: بدونه بيصير
`tests/aipipeline/conftest.py` موديولًا اسمه `conftest` بمستوى القمة،
فبيحجب `tests/conftest.py` — وتمانية من اختبارات المحرر بتعمل
`from conftest import ...` وبتنكسر عند الجمع.

والاسم بلا شرطة سفلية (`aipipeline` مش `ai_pipeline`) بقصد كمان:
كحزمة، الاسم بينحلّ عن `tests/`، فـ`ai_pipeline` كان بيصير يشير
لمجلّد الاختبارات بدل الحزمة الحقيقية:

    ModuleNotFoundError: No module named 'ai_pipeline.models'
"""
