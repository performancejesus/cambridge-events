"""31. Подтверждённые открытия не теряются (исправляющая; правки по v9: Arbury Social 25.09 и Bridge Bagels 28.09 из
находок 6b пропали, хотя попадают в окно «последние 2 месяца» — рубрика была заполнена более слабыми пунктами).
Открытие в Кембридже, подтверждённое на странице (S148, дата из текста) и ещё не показанное, должно быть в «Новом в
городе»; сборка (build_issue.mandatory) освобождает место, вытесняя открытия, известные только по дате статьи."""

from __future__ import annotations

import re

from . import FIX, Finding

RULE, TITLE, LEVEL = 31, "Подтверждённые открытия (S148) — в «Новом в городе» (правки по v9)", FIX


def check(ctx) -> Finding:
    f = Finding()
    placed = {i for rub, it in ctx.model_items() if rub == "new_in_town" for i in it["ids"]}
    for cid, c in ctx.pools.candidates.items():
        if c["kind"] == "venue_news" and "S148" in (c.get("sources") or []) and c.get("date_basis") == "stated" \
                and c.get("date") and c.get("stage") == "opened" and re.search(r"\bCambridge\b", c.get("address") or "") \
                and cid not in placed:
            f.violations.append(f"«{c['title']}» (открылось {c['date']}) — не в «Новом в городе»")
    return f
