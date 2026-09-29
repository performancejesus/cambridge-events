"""Этап 6b: подтверждённые находки поиска Keenable → база (источник S148 «Keenable — поиск»).

1. События: пропуски (search_gaps) со статусом verified — название и дата рядом на странице — в зоне, с датой ≥ даты
   прогона → data/raw/S148_keenable.json → обычный конвейер update_db (дедупликация, площадки, зоны). Описание —
   фрагмент проверенной страницы вокруг названия (для модели выпуска, не публикуется).
2. Открытия и закрытия: verified с датой (из результата или даты публикации страницы) не старше 2026-07-01 → venue_news
   (source_type = search).
3. Пункты только из газет с ИИ-запретом (newspaper_primary), у которых поиск нашёл первоисточник или агрегатор: страница
   проверяется (название и дата рядом) → запись S148 склеивается с событием; основной ссылкой становится первоисточник
   (ingest.rank: газеты с ИИ-запретом — после S148).

  python scripts/load_search_findings.py && python scripts/update_db.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from collectors.base import RawEvent  # noqa: E402
from collectors.http import Disallowed, FetchError, PoliteClient  # noqa: E402
from gap_audit import LISTED, TODAY, _words, near, page_clean, page_text  # noqa: E402
from pipeline import domains  # noqa: E402
from pipeline.db import connect  # noqa: E402

SID = "S148"
RAW = ROOT / "data" / "raw"
OPENINGS_SINCE = "2026-07-01"


def context(http, url: str, name: str, span: int = 450) -> str:
    """Фрагмент читаемого текста страницы (без скриптов) вокруг названия: описание для модели выпуска, не публикуется."""
    try:
        text = page_clean(http, url)
    except Exception:  # noqa: BLE001
        return ""
    words = sorted(_words(name), key=len, reverse=True)
    low = text.lower()
    i = low.find(words[0]) if words else -1
    return text[max(0, i - 60):i + span].strip() if i >= 0 else ""


REVIEW = json.loads((ROOT / "data" / "search_review.json").read_text())
REJECT = {int(k): v for k, v in REVIEW["reject"].items()}
FIX = {int(k): v for k, v in REVIEW.get("fix", {}).items()}   # исправленные поля (первоисточник найден и проверен)


def events(con, http) -> list[RawEvent]:
    out = []
    for g in con.execute("""SELECT * FROM search_gaps WHERE kind='event' AND verify='verified' AND date_start >= ?""",
                         (TODAY,)).fetchall():
        if g["zone"] not in LISTED or g["gap_id"] in REJECT:
            continue
        fx = FIX.get(g["gap_id"], {})
        g = dict(g) | {k: v for k, v in fx.items() if k in ("name", "venue", "town", "time")} | \
            ({"verify_url": fx["url"]} if "url" in fx else {})
        start = g["date_start"] + (f"T{g['time'][:5]}" if g["time"] and re.match(r"\d\d:\d\d", g["time"]) else "")
        out.append(RawEvent(source_id=SID, title=g["name"], url=g["verify_url"], start=start,
                            end=g["date_end"] if g["date_end"] and g["date_end"] != g["date_start"] else None,
                            venue=g["venue"], address=g["town"], postcode=fx.get("postcode"), price=g["price"],
                            categories=[g["category"]] if g["category"] and g["category"] != "none" else [],
                            summary=context(http, g["verify_url"], g["name"]) or None, external_id=f"gap:{g['gap_id']}"))
    return out


def openings(con) -> int:
    n = 0
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for g in con.execute("SELECT * FROM search_gaps WHERE kind IN ('opening','closure') AND verify='verified'").fetchall():
        if g["gap_id"] in REJECT:
            continue
        pubs = [r[0][:10] for r in con.execute(f"""SELECT published_at FROM search_results WHERE url IN
            ({','.join('?' * len(json.loads(g['urls'])))}) AND published_at IS NOT NULL""", json.loads(g["urls"]))]
        date, basis = (g["date_start"], "stated") if g["date_start"] else ((min(pubs), "publication_date") if pubs else (None, None))
        if not date or date < OPENINGS_SINCE:
            continue
        cur = con.execute("""INSERT OR IGNORE INTO venue_news(name, type, address, postcode, stage, date, source_id,
            source_type, url, note, first_seen_at, date_basis) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                          (g["name"], None, ", ".join(x for x in (g["venue"], g["town"]) if x), None,
                           "closed" if g["kind"] == "closure" else "opened", date, SID, "search", g["verify_url"],
                           f"найдено поиском Keenable (этап 6b), название проверено на странице {domains.host(g['verify_url'])}",
                           now, basis))
        n += cur.rowcount
    return n


def primaries(con, http) -> tuple[list[RawEvent], dict]:
    """Газетные пункты с найденным первоисточником: страница проверяется (название и дата рядом) → запись S148 с теми же
    названием, датой и площадкой — дедупликация склеит её с событием, основной ссылкой станет первоисточник."""
    st = {"checked": 0, "verified": 0}
    out = []
    fixes = json.loads((ROOT / "data" / "newspaper_primary_review.json").read_text())
    for r in con.execute("""SELECT * FROM newspaper_primary WHERE best_type IN ('primary','aggregator')
                            AND item_key LIKE 'event:%'""").fetchall():
        if fixes.get(r["item_key"], {}).get("best_type") in ("none", "other_media"):
            continue
        st["checked"] += 1
        try:
            text = page_text(http, r["best_url"])
        except (Disallowed, FetchError, Exception):  # noqa: BLE001
            continue
        words = sorted(_words(r["name"]))
        found = [w for w in words if w in text]
        ok = bool(words) and len(found) >= max(1, round(0.6 * len(words))) and bool(r["date"]) and \
            near(text, found or words, r["date"])
        con.execute("UPDATE newspaper_primary SET note = note || ? WHERE item_key=? AND note NOT LIKE '%страница проверена%'",
                    (" [страница проверена: название и дата]" if ok else " [страница проверена: даты рядом с названием нет]",
                     r["item_key"]))
        if not ok:
            continue
        st["verified"] += 1
        e = con.execute("SELECT * FROM events WHERE event_id=?", (int(r["item_key"].split(":")[1]),)).fetchone()
        out.append(RawEvent(source_id=SID, title=e["title"], url=r["best_url"],
                            start=e["date_start"] + (f"T{e['time_start']}" if e["time_start"] else ""),
                            end=e["date_end"] if e["date_end"] and e["date_end"] != e["date_start"] else None,
                            venue=e["venue_name"], address=e["address"], postcode=e["postcode"], price=e["price_text"],
                            summary=context(http, r["best_url"], e["title"]) or None, external_id=f"primary:{r['item_key']}"))
    con.commit()
    return out, st


def main() -> None:
    con = connect()
    http = PoliteClient()
    evs = events(con, http)
    prim, st = primaries(con, http)
    evs += prim
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (RAW / f"{SID}_keenable.json").write_text(json.dumps([e.to_dict() for e in evs], ensure_ascii=False, indent=1))
    run = json.loads((RAW / "_run.json").read_text())
    # частичный прогон: update_db загружает только источники этого запуска (_run_id)
    run[SID] = {"name": "Keenable — поиск (этап 6b)", "module": "keenable", "started_at": started, "ok": True,
                "events": len(evs), "articles": 0, "stores": 0, "requests": 0, "seconds": 0}
    run["_run_id"] = started
    (RAW / "_run.json").write_text(json.dumps(run, ensure_ascii=False, indent=1))
    n_open = openings(con)
    con.commit()
    http.close()
    print(json.dumps({"events": len(evs) - len(prim), "venue_news": n_open, "newspaper_primary": st}, ensure_ascii=False))


if __name__ == "__main__":
    main()
