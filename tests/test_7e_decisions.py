"""Прогон 7e+ (05.10): регрессионные тесты решений после этапа 7e (без сети и API)."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pipeline import budget, history, issue, issue_fixes, recurring  # noqa: E402


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    return con


def test_drafts_do_not_count_for_repeats():
    """v5–v12 — черновики: не исключают повтор и не участвуют в отсчёте; отправленный выпуск — исключает."""
    con = _con()
    history.init(con)
    res = {"sections": [{"rubric": "weekdays", "items": [{"ids": ["E1"], "title_en": "X"}]}]}
    history.record(con, "2026-10-01", "v7", res, {"E1": {"event_ids": [1]}})
    assert history.shown_before(con, date(2026, 10, 8)) == {}
    assert history.last_sent(con, date(2026, 10, 8)) is None
    history.mark_sent(con, "2026-10-01", "v7")
    assert history.shown_before(con, date(2026, 10, 8)) == {"E": {1: "2026-10-01"}}
    assert history.last_sent(con, date(2026, 10, 8)) == "2026-10-01"


def test_old_issue_items_marked_draft():
    """Таблица без столбца status (до прогона 7e+) — после init все записи черновики."""
    con = _con()
    con.execute("""CREATE TABLE issue_items (issue_date TEXT, version TEXT, rubric TEXT, cand_id TEXT, kind TEXT,
                   event_id INTEGER, title TEXT, recorded_at TEXT, PRIMARY KEY (issue_date, version, cand_id, event_id))""")
    con.execute("INSERT INTO issue_items VALUES ('2026-10-08','v12','weekdays','E1','E',1,'X','t')")
    history.init(con)
    assert con.execute("SELECT status FROM issue_items").fetchone()[0] == "draft"


def _recurring_con() -> sqlite3.Connection:
    con = _con()
    con.execute("""CREATE TABLE recurring_events (rec_id TEXT PRIMARY KEY, name TEXT, festival INTEGER, stage TEXT,
                   stage_since TEXT, found_date TEXT, found_date_end TEXT, on_sale_note TEXT, on_sale_since TEXT,
                   last_checked_at TEXT, status_note TEXT, event_id INTEGER, tickets INTEGER)""")
    return con


def test_folk_festival_on_sale_without_start_fires_rule_39():
    """Folk Festival 2027: «в продаже» с 18.09, даты начала нет — проверка 39 срабатывает (в v12 не попал в анонсы)."""
    from tests.issue_rules.r39_festivals import on_sale_without_start
    con = _recurring_con()
    con.execute("""INSERT INTO recurring_events(rec_id, name, festival, found_date, found_date_end, on_sale_note,
                   on_sale_since, last_checked_at) VALUES ('R09','Cambridge Folk Festival',1,NULL,'2027-08-01',
                   'ранние билеты в продаже','2026-09-18','2026-10-05')""")
    row = con.execute("SELECT * FROM recurring_events").fetchone()
    stage, since = recurring.stage_of(con, row)
    assert (stage, since) == ("в продаже", "2026-09-18")
    con.execute("UPDATE recurring_events SET stage=?, stage_since=?", (stage, since))
    out = on_sale_without_start(con, date(2026, 10, 8), set())
    assert out and "нет даты начала" in out[0] and "manual_start" in out[0]
    assert not on_sale_without_start(con, date(2026, 10, 8), {"R09"})   # кандидат есть — нарушения нет
    assert not on_sale_without_start(con, date(2026, 11, 20), set())     # продажа объявлена давно — не «новый анонс»


def test_folk_festival_festival_stage_with_manual_start():
    w = issue.Window(date(2026, 10, 8), date(2026, 10, 8), date(2026, 10, 18))
    e = {"date_start": "2027-07-30", "stage": "в продаже", "stage_since": "2026-09-18"}
    assert issue.festival_stage(e, w) == ("on_sale", "билеты в продаже")


def test_zone_exception_only_named_events_and_rubrics():
    import build_issue as b
    issue._ZONE_EXC = None
    snail = {"title": "World Snail Racing Championship 2027", "zone": "out_of_zone"}
    other = {"title": "Congham village fete", "zone": "out_of_zone"}
    exc = issue.zone_exception(snail)
    assert exc and exc["rec_id"] == "R27" and issue.zone_exception(other) is None
    assert issue.zone_exception({"title": "RHS Sandringham Flower Show", "zone": "out_of_zone"})["rec_id"] == "R58"
    w = issue.Window(date(2026, 10, 8), date(2026, 10, 8), date(2026, 10, 18))
    c = {"kind": "announcement", "zone": "до часа", "zone_exception": exc, "importance": 3, "on_weekends": ["weekend_1"]}
    assert not b.fits("out_of_town", c, w) and not b.fits("weekdays", c, w)
    assert b.fits("weekend_1", c, w)


def test_jazz_festival_only_official():
    con = _con()
    con.execute("CREATE TABLE recurring_events (name TEXT, patterns TEXT, official_url TEXT, found_source TEXT, official_only TEXT)")
    con.execute("CREATE TABLE event_sources (event_id INTEGER, source_id TEXT)")
    con.execute("INSERT INTO recurring_events VALUES ('Cambridge International Jazz Festival', ?, 'https://www.cambridgejazzfestival.co.uk/', NULL, '1')",
                (json.dumps(["Cambridge Jazz Festival", "Cambridge International Jazz"]),))
    con.execute("INSERT INTO event_sources VALUES (5, 'S006')")
    e = {"event_id": 5, "title": "Cambridge International Jazz Festival 2026"}
    orig = issue._sources
    issue._sources = lambda con, eid: [r[0] for r in con.execute("SELECT source_id FROM event_sources WHERE event_id=?", (eid,))]
    try:
        assert issue.official_only_reason(con, e)
        con.execute("UPDATE recurring_events SET found_source=official_url")   # подтверждено на сайте фестиваля
        assert issue.official_only_reason(con, e) is None
    finally:
        issue._sources = orig


def test_english_duplicate_word_director():
    assert issue_fixes.en_dupes("Режиссёр Director Roddy Bogawa покажет фильм.") == [("Режиссёр", "Director")]
    assert not issue_fixes.en_dupes("Фестиваль Festival of Ideas, хор Choir of King's College")
    res = {"sections": [{"rubric": "cinema", "items": [{"ids": [], "title_en": "Cold Water", "title_ru": "Cold Water",
                                                        "blurb_ru": "Режиссёр Director Roddy Bogawa о группе."}]}]}
    assert issue_fixes.fix_en_dupes(res)
    assert res["sections"][0]["items"][0]["blurb_ru"] == "Режиссёр Roddy Bogawa о группе."


def test_nine_lessons_ballot_not_queue():
    p = issue.Pools()
    it = {"ids": [], "title_en": "A Festival of Nine Lessons and Carols", "title_ru": "A Festival of Nine Lessons and Carols",
          "blurb_ru": "Служба с хором King's College. Очередь занимают с раннего утра.",
          "blurb_en": "Queue from early morning for a seat."}
    res = {"sections": [{"rubric": "new_announcements", "items": [it]}]}
    assert issue_fixes.fix_nine_lessons(res, p)
    assert "Очередь занимают" not in it["blurb_ru"] and "онлайн-лотерее" in it["blurb_ru"]
    assert "ballot" in it["blurb_en"] and "Queue from" not in it["blurb_en"]
    assert not issue_fixes.fix_nine_lessons(res, p)   # повторно не меняет


def test_budget_credit_error_blocks(monkeypatch, tmp_path):
    con = _con()
    con.execute("CREATE TABLE llm_usage (called_at TEXT, purpose TEXT, model TEXT, article_id INTEGER, "
                "input_tokens INTEGER, output_tokens INTEGER, cost_usd REAL)")
    con.execute("INSERT INTO llm_usage VALUES ('2026-10-01T10:00:00+00:00','issue 2026-10-08_v12','m',NULL,0,0,0.8)")
    con.execute("INSERT INTO llm_usage VALUES ('2026-10-01T10:05:00+00:00','issue claims x','m',NULL,0,0,1.2)")
    monkeypatch.setattr(budget, "NOTIFY_FILE", tmp_path / "n.jsonl")
    monkeypatch.setattr(budget, "BALANCE_FILE", tmp_path / "b.json")
    assert budget.estimate(con)["issue_build_usd"] == 2.0
    monkeypatch.setattr(budget, "probe", lambda: {"ok": False, "error": "Your credit balance is too low", "credit": True})
    try:
        budget.preflight(con)
        raise AssertionError("должно было остановить сборку")
    except budget.BalanceEmpty:
        pass
    assert "api_balance_empty" in (tmp_path / "n.jsonl").read_text()
    monkeypatch.setattr(budget, "probe", lambda: {"ok": True, "error": None, "credit": False})
    (tmp_path / "b.json").write_text(json.dumps({"balance_usd": 5.0, "as_of": "2026-10-01T00:00:00+00:00"}))
    assert budget.preflight(con)["status"] == "ok_week_short"   # остаток 3.0 ≥ прогона 2.0, но < недели 5.5
    (tmp_path / "b.json").write_text(json.dumps({"balance_usd": 2.5, "as_of": "2026-10-01T00:00:00+00:00"}))
    try:
        budget.preflight(con)
        raise AssertionError("остаток меньше прогона — стоп")
    except budget.BalanceEmpty:
        pass


def test_junction_request_budget():
    """Junction после паузы — не больше ≈ 20 сетевых запросов: известные страницы событий не перезапрашиваются."""
    from collectors.sources.junction import Junction

    class FakeHttp:
        requests = 0

        def get(self, url):
            self.requests += 1
            n = self.requests

            class R:
                text = "".join(f'<a href="https://www.junction.co.uk/events/e{n}-{i}/">x</a>' for i in range(12))
            return R()

    c = Junction()
    c.cache = {}
    http = FakeHttp()
    links = c.links(http)
    c.start_details()
    for link in links:
        c.detail(http, link)
    assert http.requests <= c.request_budget


def test_junction_day_limit(tmp_path, monkeypatch):
    """Суточный лимит Junction — для всех модулей вместе (сбор, статусы, ссылки)."""
    from collectors import http as H
    con = H.state(tmp_path / "s.db")
    c = H.PoliteClient.__new__(H.PoliteClient)
    c.db, c.stats = con, {"deferred": 0}
    c.purpose = "test"
    now = H._iso(H._now())
    for _ in range(H.HOST_DAY_LIMITS["www.junction.co.uk"]):
        con.execute("INSERT INTO request_log VALUES (?,?,?,?,?,?,?)", (now, "www.junction.co.uk", "u", "x", "network", 200, 1))
    try:
        c._check_host("www.junction.co.uk", "https://www.junction.co.uk/events/x/")
        raise AssertionError("лимит должен сработать")
    except H.Deferred:
        pass
    c._check_host("www.kettlesyard.co.uk", "https://www.kettlesyard.co.uk/")   # у других доменов — общий лимит 250
