"""58. «Фестивали» (исправляющая; новая рубрика 11.10): календарь из recurring_events — фестиваль в рубрике, когда до него
меньше 10 недель или открыта продажа; в реестре есть Cambridge Pride и театральные фестивали (Cambridge Shakespeare
Festival); Jazz Festival — только после подтверждения на сайте фестиваля."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 58, "«Фестивали»: все ближайшие и в продаже; Pride и театральные — в реестре", FIX
MUST_HAVE = {"Cambridge Pride": "R25", "Cambridge Shakespeare Festival": "R36"}


def check(ctx) -> Finding:
    from pipeline import festivals
    f = Finding()
    ids = festivals.calendar_ids()
    names = {r["rec_id"]: r["name"] for r in ctx.con.execute("SELECT rec_id, name FROM recurring_events")}
    for name, rid in MUST_HAVE.items():
        if rid not in names or rid not in ids:
            f.violations.append(f"«{name}» нет в календаре фестивалей реестра")
    shown = {it["ids"][0] for rub, it in ctx.model_items() if rub == "festivals" and it["ids"]}
    placed = {e for rub, it in ctx.model_items() if rub != "festivals" for i in it["ids"]
              for e in (ctx.pools.candidates.get(i) or {}).get("event_ids", [])}
    for r in ctx.con.execute("SELECT * FROM recurring_events").fetchall():
        if r["rec_id"] not in ids:
            continue
        ok, why = festivals.due(r, ctx.w.issue)
        run = (getattr(ctx.pools, "running_festivals", {}) or {}).get(r["rec_id"])   # этап 7h: карточка фестиваля окна
        card = run and set((ctx.pools.candidates.get(run) or {}).get("event_ids", [])) & placed
        if ok and f"R:{r['rec_id']}" not in shown and not (r["event_id"] and r["event_id"] in placed) and not card:
            f.violations.append(f"«{r['name']}»: {why}, но нет ни в «Фестивалях», ни полной карточкой")
    f.info.append(f"строк в «Фестивалях»: {len(shown)}; фестивалей в реестре: {len(ids)}")
    return f
