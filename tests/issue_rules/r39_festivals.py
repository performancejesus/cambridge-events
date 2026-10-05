"""39. Ежегодные фестивали (исправляющая; этап 7d, п. 5): как только объявлены дата или продажа билетов — пункт в
«Новых анонсах»; за 4–6 недель до начала — напоминание. Фестивали списка (recurring_events.festival: Folk Festival,
Strawberry Fair, Cambridge Pride, Stourbridge Fair, Mill Road Winter Fair, Midsummer Fair, Big Weekend, фейерверки,
рождественские огни) в остальных выпусках не повторяются. Дописывает build_issue.mandatory.

Прогон 7e+ (решение после 7e, 01.10): срабатывает и на фестиваль «в продаже» без даты начала (Folk Festival 2027 —
ранние билеты с 18.09, а на сайте только окончание): кандидата для «Новых анонсов» у такого фестиваля нет, поэтому
нарушение — «внести manual_start» (в v12 Folk Festival из-за этого не попал в анонсы)."""

from __future__ import annotations

from datetime import timedelta

from pipeline.issue import ANNOUNCE_DAYS

from . import FIX, Finding

RULE, TITLE, LEVEL = 39, "Ежегодные фестивали: анонс при новой дате или продаже, напоминание за 4–6 недель", FIX
STAGE_RU = {"announced": "дата объявлена", "on_sale": "билеты в продаже", "reminder": "напоминание"}


def on_sale_without_start(con, issue, have: set[str]) -> list[str]:
    """Фестивали «в продаже» (продажа объявлена за ANNOUNCE_DAYS до выпуска) без даты начала (found_date пуст): события
    в базе нет, кандидата для «Новых анонсов» тоже."""
    cols = {r[1] for r in con.execute("PRAGMA table_info(recurring_events)")}
    if "stage" not in cols:
        return []
    since = (issue - timedelta(days=ANNOUNCE_DAYS)).isoformat()
    out = []
    for r in con.execute("""SELECT rec_id, name, found_date, found_date_end, stage_since FROM recurring_events
                            WHERE festival=1 AND stage='в продаже' AND found_date IS NULL
                            AND substr(coalesce(stage_since, ''), 1, 10) >= ?""", (since,)):
        if r["rec_id"] in have:
            continue
        end = f", окончание {r['found_date_end']}" if r["found_date_end"] else ""
        out.append(f"«{r['name']}» ({r['rec_id']}): в продаже с {(r['stage_since'] or '')[:10]}{end}, но нет даты начала — "
                   f"нет кандидата для «Новых анонсов»; внести manual_start в data/recurring_events.json")
    return out


def check(ctx) -> Finding:
    f = Finding()
    placed = {e for rub, it in ctx.model_items() for i in it["ids"]
              for e in (ctx.pools.candidates.get(i) or {}).get("event_ids", [])}
    due = [(cid, c) for cid, c in ctx.pools.candidates.items() if c.get("festival")]
    for cid, c in due:
        if not set(c["event_ids"]) & placed:
            f.violations.append(f"«{c['title']}» ({STAGE_RU.get(c['festival']['stage'])}): нет в выпуске")
    have = {c["festival"]["rec_id"] for _, c in due}
    f.violations += on_sale_without_start(ctx.con, ctx.w.issue, have)
    f.info.append("фестивалей к показу: " + (", ".join(f"{c['title']} — {STAGE_RU.get(c['festival']['stage'])}"
                                                    for _, c in due) or "нет"))
    return f
