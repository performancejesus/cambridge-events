"""12. Тон (исправляющая): фразы давления и оценочные преувеличения без сигнала срочности со страницы удаляются
(build_issue.check_tone); проверка — в итоговом тексте таких фраз нет."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 12, "Тон без давления", FIX


def check(ctx) -> Finding:
    from scripts.build_issue import PRESSURE_EN, PRESSURE_RU
    f = Finding()
    for rub, it in ctx.model_items():
        urgent = any((ctx.pools.candidates.get(i) or {}).get("page_urgency") or (ctx.pools.candidates.get(i) or {}).get("urgency")
                     for i in it["ids"])
        for fld, rx in (("blurb_ru", PRESSURE_RU), ("blurb_en", PRESSURE_EN)):
            for m in rx.finditer(it.get(fld) or ""):
                hype = any(x in m.group(0).lower() for x in ("на пике", "самого важного", "самых важных", "at the peak", "biggest year"))
                if hype or not urgent:
                    f.violations.append(f"«{it['title_ru']}»: «{m.group(0).strip()[:90]}»")
    for lang, rx in (("ru", PRESSURE_RU), ("en", PRESSURE_EN)):
        for m in rx.finditer(ctx.result.get(f"intro_{lang}") or ""):
            f.violations.append(f"вступление: «{m.group(0).strip()[:90]}»")
    return f
