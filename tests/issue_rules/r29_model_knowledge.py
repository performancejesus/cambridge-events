"""29. Факты из знаний модели — в «Факты из знаний модели (проверить)» (исправляющая; правки по v9).

Утверждения описаний, которых нет в тексте источника пункта (сверка claims.py: «нет в источнике») или которые с ним
расходятся («искажено»), сборка переносит в список пункта knowledge_ru / knowledge_en с пометкой «сверка». Примеры v9:
Philippa Gregory — «Eleanor Cobham при дворе Генриха V» (известна при дворе Генриха VI); Maddy Prior — «Nic James»
(Nic Jones?); Cambridge United — «матч Лиги Two» (лигу сезона сверять с сайтом клуба, см. проверку 30). Для темы недели
и пунктов из статей «искажено» блокирует выпуск (проверка 2)."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 29, "Факты из знаний модели — в список «проверить» (правки по v9)", FIX
MARK = "сверка"


def check(ctx) -> Finding:
    f = Finding()
    if ctx.claims is None:
        f.skipped = "сверка с источниками не выполнялась"
        return f
    listed = {}
    for rub, it in ctx.model_items():
        listed[it.get("title_ru") or it.get("title_en")] = " ".join(it.get("knowledge_ru") or [])
    n = 0
    for key, claims in ctx.claims.get("items", {}).items():
        if key not in listed:
            continue
        for c in claims:
            if c["verdict"] in ("not_in_source", "distorted"):
                n += 1
                if c["claim_ru"][:60] not in listed[key]:
                    f.violations.append(f"«{key}»: «{c['claim_ru']}» ({'искажено' if c['verdict'] == 'distorted' else 'нет в источнике'}) — не в списке «проверить»")
    f.info.append(f"утверждений не из источника: {n}")
    return f
