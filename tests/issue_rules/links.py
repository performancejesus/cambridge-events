"""Проверка ссылок выпуска (для правила 7): одна загрузка страницы нашим ботом (robots.txt, паузы), кэш на сутки —
таблица link_checks. Закрытое robots.txt не проверяем и не обходим."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

SCHEMA = "CREATE TABLE IF NOT EXISTS link_checks (url TEXT PRIMARY KEY, status TEXT, detail TEXT, checked_at TEXT)"


def hrefs(html: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r'href="([^"]+)"', html or "")))


def check_urls(con, urls: list[str], http, max_age_hours: int = 20) -> dict[str, dict]:
    from collectors.http import Disallowed, FetchError
    con.execute(SCHEMA)
    out = {}
    fresh = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
    for u in urls:
        r = con.execute("SELECT status, detail FROM link_checks WHERE url=? AND checked_at>=?", (u, fresh)).fetchone()
        if r:
            out[u] = {"status": r[0], "detail": r[1]}
            continue
        try:
            resp = http.get(u)
            st, det = "ok", str(resp.status)
        except Disallowed:
            st, det = "disallowed", "robots.txt не разрешает"
        except FetchError as e:
            m = re.search(r"HTTP (\d{3})", str(e))
            st, det = (("dead" if m.group(1) in ("404", "410") else "error"), m.group(1)) if m else ("error", str(e)[:120])
        except Exception as e:  # noqa: BLE001
            st, det = "error", f"{type(e).__name__}"
        con.execute("INSERT OR REPLACE INTO link_checks VALUES (?,?,?,?)",
                    (u, st, det, datetime.now(timezone.utc).isoformat(timespec="seconds")))
        con.commit()
        out[u] = {"status": st, "detail": det}
    return out
