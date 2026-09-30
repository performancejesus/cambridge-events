"""Решения после этапа 6d: список источников для замера ИИ-запретов — автоматически по robots.txt всех источников.

Для каждого источника реестра — хосты из колонок «URL» и «Endpoint для сбора» (не ссылки событий: те ведут на площадки
и продавцов). robots.txt каждого хоста (pipeline.domains, свежая проверка) → каким агентам Anthropic закрыт корень.
Группы для замера:
  - claude_user — закрыт Claude-User (агент по запросу пользователя; режим claude_user_only);
  - training    — закрыты только боты обучения/поиска (ClaudeBot, anthropic-ai, Claude-Web, Claude-SearchBot).
Таблица source_ai_auto и data/ai_sources.json. Флаг respect_ai_disallow здесь не меняется — это только замер.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import openpyxl

from . import domains
from .db import ROOT

# этап 7b: реестр v0.9 (Cambridge Union, NGS, Light, колледжи); пока его нет — v0.8
REGISTRY = next(p for p in (ROOT / "data" / "cambridge_event_sources_v0.9.xlsx",
                            ROOT / "data" / "cambridge_event_sources_v0.8.xlsx") if p.exists())
SCHEMA = """CREATE TABLE IF NOT EXISTS source_ai_auto (
    source_id TEXT, host TEXT, agents TEXT, grp TEXT, checked_at TEXT, PRIMARY KEY (source_id, host)
)"""
OUT = ROOT / "data" / "ai_sources.json"


def source_hosts() -> dict[str, set[str]]:
    wb = openpyxl.load_workbook(REGISTRY, read_only=True)
    rows = list(wb["Источники"].iter_rows(values_only=True))
    head = rows[0]
    iu, ie, iid = head.index("URL"), head.index("Endpoint для сбора"), head.index("ID")
    out: dict[str, set[str]] = {}
    for r in rows[1:]:
        for u in (r[iu], r[ie]):
            if r[iid] and u and str(u).startswith("http"):
                out.setdefault(r[iid], set()).add(domains.host(str(u)))
    return out


def refresh(con: sqlite3.Connection, max_age_days: int = 7) -> dict:
    """Перепроверить robots.txt хостов источников (старше max_age_days) и пересобрать группы."""
    con.execute(SCHEMA)
    domains.robots(con)
    hosts = source_hosts()
    all_hosts = {h for hs in hosts.values() for h in hs}
    cutoff = datetime.now(timezone.utc).timestamp() - max_age_days * 86400
    stale = {r[0] for r in con.execute("SELECT host, checked_at FROM domain_robots")
             if datetime.fromisoformat(r[1]).timestamp() < cutoff}
    con.executemany("DELETE FROM domain_robots WHERE host=?", [(h,) for h in stale & all_hosts])
    checked = domains.check(con, all_hosts)
    rb = domains.robots(con)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    con.execute("DELETE FROM source_ai_auto")
    groups: dict[str, list] = {"claude_user": [], "training": []}
    for sid, hs in sorted(hosts.items()):
        for h in sorted(hs):
            agents = (rb.get(h)["ai_blocked"] if rb.get(h) else "") or ""
            grp = "claude_user" if "Claude-User" in agents.split(",") else ("training" if agents else "")
            con.execute("INSERT OR REPLACE INTO source_ai_auto VALUES (?,?,?,?,?)", (sid, h, agents, grp, now))
            if grp and sid not in groups[grp]:
                groups[grp].append(sid)
    groups["training"] = [s for s in groups["training"] if s not in groups["claude_user"]]
    con.commit()
    OUT.write_text(json.dumps({"checked_at": now, "hosts_checked": checked, "sources": len(hosts)} | groups,
                              ensure_ascii=False, indent=1))
    return {"sources": len(hosts), "hosts_checked": checked, "claude_user": len(groups["claude_user"]),
            "training": len(groups["training"])}


def groups(con: sqlite3.Connection | None = None) -> tuple[set[str], set[str]]:
    """(закрыт Claude-User, закрыты только боты обучения/поиска) — из последней проверки."""
    if OUT.exists():
        d = json.loads(OUT.read_text())
        return set(d["claude_user"]), set(d["training"])
    return set(), set()
