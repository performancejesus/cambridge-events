"""2. Пересказ источника (блокирующая).

Для темы недели, вступлений и пунктов из статей ключевые утверждения описания должны находиться в тексте источника:
сверка Haiku «есть / нет / искажено» (tests/issue_rules/claims.py). «Искажено» — блок (пример из v9: «футбольный матч,
о котором попросила его сестра», а в статье — сборы с матча идут на благотворительность). «Нет в источнике» — в
«Факты из знаний модели (проверить)» (проверка 29).
"""

from __future__ import annotations

from . import BLOCK, Finding

RULE, TITLE, LEVEL = 2, "Пересказ источника (тема недели, вступления, пункты из статей)", BLOCK


def check(ctx) -> Finding:
    f = Finding()
    if ctx.claims is None:
        f.skipped = "сверка с источниками не выполнялась (нет ключа API или --no-api)"
        return f
    n = 0
    for key, claims in ctx.claims.get("items", {}).items():
        if not ctx.claims.get("strict", {}).get(key):
            continue
        n += 1
        for c in claims:
            if c["verdict"] == "distorted":
                f.violations.append(f"«{key}»: «{c['claim_ru']}» — искажено; в источнике: «{c['evidence'][:160]}»")
    f.info.append(f"пунктов сверено строго: {n}")
    return f
