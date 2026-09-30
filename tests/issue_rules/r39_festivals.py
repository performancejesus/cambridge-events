"""39. Ежегодные фестивали (исправляющая; этап 7d, п. 5): как только объявлены дата или продажа билетов — пункт в
«Новых анонсах»; за 4–6 недель до начала — напоминание. Фестивали списка (recurring_events.festival: Folk Festival,
Strawberry Fair, Cambridge Pride, Stourbridge Fair, Mill Road Winter Fair, Midsummer Fair, Big Weekend, фейерверки,
рождественские огни) в остальных выпусках не повторяются. Дописывает build_issue.mandatory."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 39, "Ежегодные фестивали: анонс при новой дате или продаже, напоминание за 4–6 недель", FIX
STAGE_RU = {"announced": "дата объявлена", "on_sale": "билеты в продаже", "reminder": "напоминание"}


def check(ctx) -> Finding:
    f = Finding()
    placed = {e for rub, it in ctx.model_items() for i in it["ids"]
              for e in (ctx.pools.candidates.get(i) or {}).get("event_ids", [])}
    due = [(cid, c) for cid, c in ctx.pools.candidates.items() if c.get("festival")]
    for cid, c in due:
        if not set(c["event_ids"]) & placed:
            f.violations.append(f"«{c['title']}» ({STAGE_RU.get(c['festival']['stage'])}): нет в выпуске")
    f.info.append("фестивалей к показу: " + (", ".join(f"{c['title']} — {STAGE_RU.get(c['festival']['stage'])}"
                                                    for _, c in due) or "нет"))
    return f
