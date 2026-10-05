"""45. Культурные реалии (исправляющая; этап 7e, правки по v11): Father Christmas ≠ «Дед Мороз» (Father Christmas или
«Санта»); pantomime — «пантомима (рождественское семейное шоу)», Bonfire Night — с пояснением при первом упоминании.
Глоссарий — pipeline/glossary.py (тот же для выпуска и «Каникул»); исправляет issue_fixes.fix_realia.

Прогон 7e+ (решение 01.10): King's Nine Lessons and Carols — очереди больше нет, только онлайн-лотерея (ballot); в
анонсе — дата открытия лотереи (когда известна) и ссылка; исправляет issue_fixes.fix_nine_lessons."""

from __future__ import annotations

import re

from . import FIX, Finding

RULE, TITLE, LEVEL = 45, "Культурные реалии: Father Christmas, panto, Bonfire Night — без подмены", FIX


def check(ctx) -> Finding:
    from pipeline.glossary import REALIA_EXPLAIN
    from pipeline.issue_fixes import BALLOT_RU_RE, NINE_RE, NO_QUEUE_RE, QUEUE_RE, nine_lessons_ballot, ru_date
    f = Finding()
    for where, text in ctx.texts("ru"):
        if re.search(r"\bДед(?:ушк\w*)?\w* Мороз\w*", text):
            f.violations.append(f"«{where}»: «Дед Мороз» вместо Father Christmas / «Санта»")
    for rub, it in ctx.model_items():
        src = " ".join(str(c.get(k) or "") for i in it["ids"] if i in ctx.pools.candidates
                       for c in [ctx.pools.candidates[i]] for k in ("title", "summary"))
        b = it.get("blurb_ru") or ""
        for src_rx, word_rx, expl in REALIA_EXPLAIN:
            if re.search(src_rx, src, re.I) and re.search(word_rx, b, re.I) and expl not in b:
                f.violations.append(f"«{it['title_ru']}»: нет пояснения «{expl}»")
        if NINE_RE.search(f"{it.get('title_en')} {it.get('title_ru')} {src}"):
            ballot = nine_lessons_ballot(None)
            if any(QUEUE_RE.search(x) and not NO_QUEUE_RE.search(x) for x in re.split(r"(?<=[.!?])\s+", b)):
                f.violations.append(f"«{it['title_ru']}»: про очередь — очереди больше нет, только онлайн-лотерея")
            elif not BALLOT_RU_RE.search(b):
                f.violations.append(f"«{it['title_ru']}»: нет формулировки про онлайн-лотерею")
            elif ballot.get("opens") and ru_date(ballot["opens"]) not in b:
                f.violations.append(f"«{it['title_ru']}»: нет даты открытия лотереи ({ballot['opens']})")
    return f
