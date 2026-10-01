"""40. Необычные местные традиции (исправляющая; этап 7e, п. 3): событие с тегом quirky (recurring_events.tags) —
дата объявлена → «Новые анонсы»; в выходные окна или за 2–4 недели — заранее, в «Главном на выходные» (или анонсом,
если дата за окном), и в тексте одна фраза о том, что это за традиция (из recurring_events.description).
Дописывает build_issue.mandatory, объяснение — промпт (правило 9)."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 40, "Необычные традиции: анонс, «Главное на выходные» с объяснением обычая", FIX


def check(ctx) -> Finding:
    f = Finding()
    placed: dict[int, tuple[str, dict]] = {}
    for rub, it in ctx.model_items():
        for i in it["ids"]:
            for e in (ctx.pools.candidates.get(i) or {}).get("event_ids", []):
                placed[e] = (rub, it)
    due = [(cid, c) for cid, c in ctx.pools.candidates.items() if c.get("quirky")]
    for cid, c in due:
        hit = next((placed[e] for e in c["event_ids"] if e in placed), None)
        if not hit:
            f.violations.append(f"«{c['title']}» (традиция {c['quirky']['rec_id']}): нет в выпуске")
            continue
        rub, it = hit
        if c["kind"] == "event" and c.get("on_weekends") and not rub.startswith("weekend_"):
            f.violations.append(f"«{c['title']}»: традиция в выходные окна — не в «Главном на выходные» ({rub})")
        if len((it.get("blurb_ru") or "").split()) < 8:
            f.violations.append(f"«{c['title']}»: нет объяснения, что это за традиция")
    f.info.append("традиций к показу: " + (", ".join(c["title"] for _, c in due) or "нет"))
    return f
