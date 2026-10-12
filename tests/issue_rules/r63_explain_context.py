"""63. Пояснение соответствует контексту (блокирующая; правка 1 после v14): «дизайны Морриса (английский народный
танец)» — William Morris принят за morris dance. Пояснение из словаря (issue_fixes.EXPLAIN, glossary.REALIA_EXPLAIN)
допустимо, только если термин в этом смысле есть в данных пункта. Находка сверки утверждений про такое пояснение (оно
ушло в «Факты из знаний модели (проверить)») — тоже нарушение: выпуск не отправлять, пока пояснение не убрано."""

from __future__ import annotations

import re

from . import BLOCK, Finding

RULE, TITLE, LEVEL = 63, "Пояснение соответствует контексту (не к имени: William Morris ≠ morris dance)", BLOCK


def check(ctx) -> Finding:
    from pipeline.glossary import REALIA_EXPLAIN
    from pipeline.issue_fixes import _cands, wrong_explanations
    f = Finding()
    for rub, it in ctx.model_items():
        src = " ".join(str(c.get(k) or "") for c in _cands(ctx.pools, it) for k in ("title", "summary"))
        for expl in wrong_explanations(it, src):
            f.violations.append(f"«{it.get('title_ru')}»: пояснение «{expl}» не по контексту — в данных нет этого термина")
        b = f"{it.get('blurb_ru') or ''} {' '.join(it.get('knowledge_ru') or [])}"
        for src_rx, _, expl in REALIA_EXPLAIN:
            if expl in b and not re.search(src_rx, src, re.I):
                f.violations.append(f"«{it.get('title_ru')}»: пояснение «{expl}» не по контексту")
    return f
