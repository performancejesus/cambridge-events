"""Баланс Claude API перед сборкой (решение после 7e, 01.10: баланс кончился посреди сборки v12).

Что можно узнать и что нельзя: у обычного ключа API нет метода «остаток на счёте» (он виден только в Console). Поэтому:
1. **Пробный запрос** — самый дешёвый вызов (Haiku, 1 токен ответа, ≈ $0.00001). Ответ «credit balance is too low» —
   баланс пуст: сборка не стартует (код выхода 3), владельцу — уведомление.
2. **Оценка расхода** по журналу `llm_usage`: средняя стоимость последних сборок выпуска (`issue …`) и средний суточный
   расход сбора (извлечение, оценка важности, списки) → расход этого прогона и недели.
3. **Остаток — если владелец указал сумму** после пополнения: `data/api_balance.json`
   `{"balance_usd": 20.0, "as_of": "2026-10-05T00:00:00+00:00", "note": "…"}`; остаток = сумма − расход по `llm_usage`
   с этой даты. Остаток меньше недельного расхода — уведомление «на неделю не хватает».
Уведомления — `data/notifications.jsonl` (строка JSON на событие) и вывод в консоль; в этапе 8 их отправляет рассылка.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

from .db import ROOT

BALANCE_FILE = ROOT / "data" / "api_balance.json"
NOTIFY_FILE = ROOT / "data" / "notifications.jsonl"
PROBE_MODEL = "claude-haiku-4-5"
COLLECT_PURPOSES = ("article_extract", "list_extract", "importance", "venue_locate", "lineup", "regional cinema",
                    "kids_collect", "courses_collect", "places_profile", "union termcard")
CREDIT_MARKERS = ("credit balance", "billing", "insufficient", "purchase credits")


class BalanceEmpty(RuntimeError):
    """Пробный запрос отклонён из-за баланса — сборку не начинать."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def notify(kind: str, text: str, **extra) -> None:
    rec = {"at": _now().isoformat(timespec="seconds"), "kind": kind, "text": text} | extra
    with NOTIFY_FILE.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[уведомление владельцу] {text}")


def probe(api_key: str | None = None) -> dict:
    """{ok, error, credit}: пробный вызов API. credit=True — отказ из-за баланса."""
    key = api_key or os.environ.get("EVENTS_ANTHROPIC_KEY")
    if not key:
        return {"ok": False, "error": "нет ключа EVENTS_ANTHROPIC_KEY", "credit": False}
    import anthropic
    try:
        anthropic.Anthropic(api_key=key, max_retries=1).messages.create(
            model=PROBE_MODEL, max_tokens=1, messages=[{"role": "user", "content": "ok"}])
        return {"ok": True, "error": None, "credit": False}
    except anthropic.APIStatusError as e:
        msg = str(e)
        return {"ok": False, "error": msg[:300], "credit": any(m in msg.lower() for m in CREDIT_MARKERS)}
    except anthropic.APIConnectionError as e:
        return {"ok": False, "error": f"сеть: {e}"[:300], "credit": False}


def estimate(con: sqlite3.Connection, builds: int = 3, days: int = 7) -> dict:
    """Расход по журналу: сборка выпуска (среднее последних `builds` сборок — основной вызов и всё, что с ним в тот же
    день по `issue …`), сбор за сутки (среднее за последние `days` дней с расходом), неделя = 7 суток сбора + сборка."""
    rows = con.execute("""SELECT purpose, cost_usd, called_at FROM llm_usage WHERE purpose LIKE 'issue 20%'
                          ORDER BY called_at DESC LIMIT ?""", (builds,)).fetchall()
    issue_costs = []
    for r in rows:   # всё «issue …» за час до и шесть часов после основного вызова — одна сборка
        t = datetime.fromisoformat(r["called_at"])
        tot = con.execute("""SELECT sum(cost_usd) FROM llm_usage WHERE purpose LIKE 'issue%' AND called_at BETWEEN ? AND ?""",
                          ((t - timedelta(hours=1)).isoformat(), (t + timedelta(hours=6)).isoformat())).fetchone()[0]
        issue_costs.append(tot or r["cost_usd"] or 0)
    issue_avg = sum(issue_costs) / len(issue_costs) if issue_costs else 4.0
    like = " OR ".join("purpose LIKE ?" for _ in COLLECT_PURPOSES)
    per_day = con.execute(f"""SELECT substr(called_at, 1, 10) d, sum(cost_usd) FROM llm_usage WHERE ({like})
                              GROUP BY d ORDER BY d DESC LIMIT ?""", (*[p + "%" for p in COLLECT_PURPOSES], days)).fetchall()
    collect_avg = sum(r[1] or 0 for r in per_day) / len(per_day) if per_day else 0.5
    return {"issue_build_usd": round(issue_avg, 2), "collect_day_usd": round(collect_avg, 2),
            "week_usd": round(issue_avg + 7 * collect_avg, 2), "builds_seen": len(issue_costs), "days_seen": len(per_day)}


def known_balance(con: sqlite3.Connection) -> dict | None:
    """Остаток по сумме, которую владелец указал после пополнения (data/api_balance.json), минус расход с той даты."""
    if not BALANCE_FILE.exists():
        return None
    b = json.loads(BALANCE_FILE.read_text())
    if b.get("balance_usd") is None or not b.get("as_of"):
        return None
    spent = con.execute("SELECT coalesce(sum(cost_usd), 0) FROM llm_usage WHERE called_at >= ?", (b["as_of"],)).fetchone()[0]
    return {"declared_usd": b["balance_usd"], "as_of": b["as_of"], "spent_since_usd": round(spent, 2),
            "remaining_usd": round(b["balance_usd"] - spent, 2)}


def preflight(con: sqlite3.Connection, need_usd: float | None = None, purpose: str = "сборка выпуска",
              strict: bool = True) -> dict:
    """Проверка перед запуском. Баланс пуст (пробный запрос отклонён) → BalanceEmpty при strict. Остаток известен и
    меньше недельного расхода → уведомление; меньше расхода этого прогона → BalanceEmpty при strict."""
    est = estimate(con)
    need = need_usd if need_usd is not None else est["issue_build_usd"]
    res = {"checked_at": _now().isoformat(timespec="seconds"), "purpose": purpose, "estimate": est, "need_usd": round(need, 2)}
    res["probe"] = probe()
    res["balance"] = known_balance(con)
    if not res["probe"]["ok"]:
        if res["probe"]["credit"]:
            notify("api_balance_empty", f"Баланс Claude API пуст — {purpose} не запускалась. Пополните баланс "
                                        f"(нужно ≈ ${need:.2f} на прогон, ≈ ${est['week_usd']:.2f} в неделю).")
            if strict:
                raise BalanceEmpty(res["probe"]["error"])
        res["status"] = "api_unavailable"
        return res
    bal = res["balance"]
    if bal is None:
        res["status"] = "ok_unknown_balance"   # ключ рабочий; остаток не известен (метода API нет)
    elif bal["remaining_usd"] < need:
        notify("api_balance_low", f"Остаток Claude API ≈ ${bal['remaining_usd']:.2f} меньше расхода прогона "
                                  f"(≈ ${need:.2f}) — {purpose} не запускалась.")
        res["status"] = "insufficient"
        if strict:
            raise BalanceEmpty(f"остаток ≈ ${bal['remaining_usd']:.2f} < ${need:.2f}")
    elif bal["remaining_usd"] < est["week_usd"]:
        notify("api_balance_week", f"Остаток Claude API ≈ ${bal['remaining_usd']:.2f} — на неделю (≈ ${est['week_usd']:.2f}) "
                                   f"не хватит; пополните до следующего выпуска.")
        res["status"] = "ok_week_short"
    else:
        res["status"] = "ok"
    return res


def describe(res: dict) -> str:
    est, bal = res["estimate"], res.get("balance")
    s = (f"пробный запрос: {'прошёл' if res['probe']['ok'] else 'ошибка — ' + str(res['probe']['error'])[:120]}; "
         f"расход прогона ≈ ${res['need_usd']:.2f}, недели ≈ ${est['week_usd']:.2f} "
         f"(сборка ≈ ${est['issue_build_usd']:.2f}, сбор ≈ ${est['collect_day_usd']:.2f} в сутки)")
    if bal:
        s += f"; остаток ≈ ${bal['remaining_usd']:.2f} (указано ${bal['declared_usd']:.2f} на {bal['as_of'][:10]})"
    else:
        s += "; остаток не известен (у ключа API нет метода баланса — укажите сумму в data/api_balance.json)"
    return s
