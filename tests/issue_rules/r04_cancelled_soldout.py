"""4. Отменённые и распроданные — не в обычных рубриках (блокирующая): только «Отменено и перенесено» или у редактора.
Статус — из базы и из последней перепроверки страницы (page_status)."""

from __future__ import annotations

from . import BLOCK, Finding

RULE, TITLE, LEVEL = 4, "Отменённые и распроданные — не в обычных рубриках", BLOCK
BAD = {"cancelled", "postponed", "sold_out", "disappeared"}


def check(ctx) -> Finding:
    f = Finding()
    have_ps = ctx.con.execute("SELECT name FROM sqlite_master WHERE name='page_status'").fetchone()
    for e in ctx.entries("ru"):
        if e["rubric"] == "cancelled":
            continue
        for c in e["cands"]:
            st = set()
            for ev in c.get("event_ids") or []:
                r = ctx.con.execute("SELECT status FROM events WHERE event_id=?", (ev,)).fetchone()
                if r:
                    st.add(r[0])
                if have_ps:
                    p = ctx.con.execute("SELECT status FROM page_status WHERE event_id=? AND result='ok'", (ev,)).fetchone()
                    if p:
                        st.add(p[0])
            if c.get("kind") == "programme" and c.get("places") == "full":
                st.add("sold_out")
            if st & BAD:
                f.violations.append(f"«{e['title']}» ({e['rubric']}): статус {', '.join(sorted(st & BAD))}")
                break
    return f
