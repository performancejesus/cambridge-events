"""20. Размер выпуска (исправляющая через дописывание или сокращение): полных пунктов 40–45, компактные строки —
отдельно; минимумы и максимумы рубрик — по таблице rubric_sizes (база, заполняется из build_issue.RUBRIC_LIMITS; меняет
редактор). Меньше минимума — нарушение, только если подходящих кандидатов хватало."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 20, "Размер выпуска и рубрик (rubric_sizes)", FIX
FULL_MIN, FULL_MAX = 40, 45


def sizes(con) -> dict[str, tuple[int, int]]:
    from scripts.build_issue import RUBRIC_LIMITS
    con.execute("CREATE TABLE IF NOT EXISTS rubric_sizes (rubric TEXT PRIMARY KEY, min_items INTEGER, max_items INTEGER, "
                "note TEXT)")
    for r, (lo, hi) in RUBRIC_LIMITS.items():
        con.execute("INSERT OR IGNORE INTO rubric_sizes VALUES (?,?,?,?)", (r, lo, hi, "из build_issue.RUBRIC_LIMITS"))
    con.commit()
    return {r: (lo, hi) for r, lo, hi in con.execute("SELECT rubric, min_items, max_items FROM rubric_sizes")}


def check(ctx) -> Finding:
    from scripts.build_issue import is_compact, fits
    f = Finding()
    lim = sizes(ctx.con)
    full = compact = 0
    got = {}
    for rub, it in ctx.model_items():
        if is_compact(it, ctx.pools):
            compact += 1
        else:
            full += 1
            got[rub] = got.get(rub, 0) + 1
    if full > FULL_MAX:
        f.violations.append(f"полных пунктов {full} — больше {FULL_MAX}")
    elif full < FULL_MIN:
        f.warnings.append(f"полных пунктов {full} — меньше {FULL_MIN}")
    used = {i for _, it in ctx.model_items() for i in it["ids"]}
    for rub in ctx.w.rubrics():
        key = "weekend" if rub.startswith("weekend_") else rub
        if key not in lim or rub in ("holidays",):
            continue
        lo, hi = lim[key]
        n = got.get(rub, 0)
        if n > hi:
            f.violations.append(f"{rub}: {n} пунктов, максимум {hi}")
        elif n < lo:
            spare = sum(1 for cid, c in ctx.pools.candidates.items() if cid not in used and cid[0] in "EATVCF"
                        and fits(rub, c, ctx.w) and not c.get("thin_data"))
            (f.violations if spare >= lo - n and key in ("free", "kids", "new_announcements", "out_of_town") else f.warnings
             ).append(f"{rub}: {n} пунктов, минимум {lo} (свободных подходящих кандидатов: {spare})")
    f.info.append(f"полных {full}, компактных {compact}")
    return f
