"""54. Дубли в выпуске (исправляющая; итоги 7f: Alice Cooper ×2, UNIQLO ×3, Arbury Social ×3, Tenpin ×2, Ely Autumn Fayre
×2 …): одно событие, одна страница или одно и то же по площадке + дате + похожему названию — один раз на весь выпуск.
Склейка — issue.merge_duplicates до модели; здесь — что не осталось."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 54, "Дубли в выпуске: одно событие / страница / площадка+дата+название — один раз", FIX


def check(ctx) -> Finding:
    from pipeline.normalize import norm_title, norm_venue, title_similarity
    f = Finding()
    rows = []
    for e in ctx.entries("en"):
        if e.get("more") or not e["cands"]:
            continue
        c = e["cands"][0]
        rows.append((e["title"], e["url"], set(c.get("event_ids") or []), {x[0] for x in c.get("dates") or [] if x},
                     norm_venue(c.get("venue") or ""), norm_title(c.get("title") or e["title"]), c.get("kind")))
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            same = (a[2] & b[2]) or (a[1] and a[1] == b[1] and a[6] not in ("course", "section", "festival")) or (
                a[3] & b[3] and a[4] and a[4] == b[4] and title_similarity(a[5], b[5]) >= 0.75)
            if same:
                f.violations.append(f"«{a[0]}» и «{b[0]}» — один пункт дважды")
    n = sum(len(v) for k, v in ctx.pools.excluded.items() if k.startswith("дубль") or "дубль" in k)
    f.info.append(f"склеено до отбора: {n}")
    return f
