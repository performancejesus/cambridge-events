"""ИИ-запреты в robots.txt (открытый вопрос брифа, флаг respect_ai_disallow).

При каждом прогоне коллекторов для источников статей проверяется robots.txt хоста статей: закрыт ли сайт для
ИИ-агентов Anthropic при том, что нашему боту он открыт. Результат — таблица source_ai_policy. Если в
data/pipeline_config.json respect_ai_disallow = true, такие источники обрабатываются без модели: заголовок RSS
и ссылка, фильтр по ключевым словам (extract.keyword_news), как Cambridge BID. По умолчанию флаг выключен.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urlparse

from .db import ROOT

CONFIG = ROOT / "data" / "pipeline_config.json"
AI_AGENTS = ("anthropic-ai", "ClaudeBot", "Claude-User", "Claude-Web", "Claude-SearchBot")


def config() -> dict:
    return json.loads(CONFIG.read_text()) if CONFIG.exists() else {}


MODES = ("off", "claude_user_only", "any_ai_agent")


def mode() -> str:
    """off — ничего не менять; claude_user_only — без модели только источники, закрывшие Claude-User (агент по
    запросу пользователя); any_ai_agent — без модели все источники с любым ИИ-запретом Anthropic. Старое булево
    значение: true → any_ai_agent, false → off."""
    v = config().get("respect_ai_disallow", "off")
    if v is True:
        return "any_ai_agent"
    if v in (False, None):
        return "off"
    if v not in MODES:
        raise ValueError(f"respect_ai_disallow: {v!r}, ожидается одно из {MODES}")
    return v


def respect_ai_disallow() -> bool:
    return mode() != "off"


def blocked_in_mode(con: sqlite3.Connection, m: str) -> set[str]:
    """Источники, которые в режиме m обрабатываются без модели (без учёта всегдашних NO_LLM)."""
    if m == "off":
        return set()
    rows = con.execute("SELECT source_id, agents FROM source_ai_policy WHERE ai_disallow=1").fetchall()
    if m == "claude_user_only":
        return {r[0] for r in rows if "Claude-User" in (r[1] or "").split(",")}
    return {r[0] for r in rows}


def check(con: sqlite3.Connection, http, source_id: str, url: str) -> list[str]:
    """Какие ИИ-агенты Anthropic не допущены к url (пусто — запрета нет). Пишет в source_ai_policy."""
    rp = http._robots_for(url)
    blocked = [a for a in AI_AGENTS if not rp.can_fetch(a, url)]
    con.execute("""INSERT OR REPLACE INTO source_ai_policy(source_id, host, ai_disallow, agents, checked_at)
        VALUES (?,?,?,?,?)""", (source_id, urlparse(url).netloc, int(bool(blocked)), ",".join(blocked),
                                datetime.now(timezone.utc).isoformat(timespec="seconds")))
    return blocked


def ai_disallowed(con: sqlite3.Connection) -> set[str]:
    return {r[0] for r in con.execute("SELECT source_id FROM source_ai_policy WHERE ai_disallow=1")}


def no_llm_sources(con: sqlite3.Connection, always: set[str]) -> set[str]:
    """Источники без модели: always (сейчас пусто) + источники, закрытые в текущем режиме флага."""
    return set(always) | blocked_in_mode(con, mode())
