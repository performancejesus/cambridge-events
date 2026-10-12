"""Этап 7g: регрессионные тесты правок после чтения v13 и итогов разметки 7f (без сети и API)."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pipeline import event_types, festivals, history, issue, issue_fixes, lines, selection  # noqa: E402


def _pools(cands: dict) -> issue.Pools:
    p = issue.Pools()
    p.candidates = cands
    return p


def _ev(title, day, t=None, venue="Saffron Hall", url=None, **kw):
    return {"kind": "event", "title": title, "dates": [(day, day, t)], "event_ids": [kw.pop("eid", hash(title) % 10000)],
            "venue": venue, "url": url, "sources": ["S017"]} | kw


def test_fagiolini_not_merged_with_gillam_and_id_fixed_by_title():
    """Правка 1: разные названия и время одного места — не дубли; пункт с чужим id получает id по названию."""
    import build_issue as b
    p = _pools({"E818": _ev("Spem In Alium: I Fagiolini at 40", "2026-10-10", "19:30", eid=818),
                "E819": _ev("Shine with Jess Gillam and her Band", "2026-10-11", "15:30", eid=819)})
    assert not issue.merge_duplicates(p)
    res = {"sections": [{"rubric": "weekend_1", "items": [{"ids": ["E819"], "title_en": "Spem In Alium: I Fagiolini at 40",
                                                           "title_ru": "Spem In Alium: I Fagiolini at 40"}]}]}
    notes = b.fix_ids_by_title(res, p)
    assert notes and res["sections"][0]["items"][0]["ids"] == ["E818"]


def test_duplicates_merged_same_venue_date_similar_title():
    p = _pools({"E1": _ev("The Bluetones | Cambridge Junction", "2026-10-20", "19:00", venue="Cambridge Junction", eid=1),
                "E2": _ev("The Bluetones", "2026-10-20", "19:00", venue="Cambridge Junction", eid=2, price_text="£30"),
                "E3": _ev("Coffee and Cake", "2026-10-20", None, venue="Royston Museum", url="https://m/events", eid=3),
                "E4": _ev("Talk: folk tales", "2026-10-20", None, venue="Royston Museum", url="https://m/events", eid=4)})
    merged = issue.merge_duplicates(p)
    assert len(merged) == 1 and len([c for c in p.candidates.values() if "Bluetones" in c["title"]]) == 1
    assert "E3" in p.candidates and "E4" in p.candidates   # одна страница-список музея — не дубль


def test_nonevents_and_dating_never():
    for t in ("Greene King Car Park Space", "Secure My Booking – Ticket Protection", "Space", "SWCHS Sixth Form Open Evening",
              "Synergy Business Networking", "October Cowork + Brunch", "Speed Dating in Cambridge Ages 40-59ish",
              "Donations page for Cambridge Comic Jam", "Modern Slavery Intelligence Network Conference 2026"):
        assert selection.nonevent_reason(t), t
    assert selection.nonevent_reason("International E-Waste Day", None, "Centre for Computing History") is None
    for t in ("Leper Chapel Open Day", "Hamlet", "Cambridge Cohousing Open Day at Marmalade Lane", "Organ recital: David Newsholme"):
        assert selection.nonevent_reason(t) is None, t


def test_frequent_regular_and_parkrun_and_vague():
    lib = {"title": "Rhymetime at Milton Road Library", "types": ["library_regular"], "dates": [("2026-10-16",) * 3]}
    assert selection.frequent_regular(lib)
    tours = {"title": "Daily guided walking tour of Cambridge", "types": [], "dates": [("2026-10-1%d" % i,) * 3 for i in range(5, 9)]}
    assert selection.frequent_regular(tours)
    play = {"title": "Hamlet", "types": ["theatre"], "dates": [("2026-10-1%d" % i,) * 3 for i in range(5, 9)]}
    assert selection.frequent_regular(play) is None
    assert selection.frequent_regular({"title": "Cambridge parkrun", "types": [], "dates": []})
    assert selection.vague({"title": "Waterstones Book Events"}) and selection.vague_reason({"title": "Studio Sunday"})
    assert selection.vague_reason({"title": "Studio Sunday", "page_facts": " ".join(["printmaking"] * 30)}) is None


def test_new_in_town_rules_and_place_normalisation():
    assert selection.norm_place("The Arbury Social") == selection.norm_place("Arbury Social")
    assert selection.news_reason({"title": "Shell petrol station", "stage": "opened"})
    assert selection.news_reason({"title": "Bistro X", "stage": "closed"})
    assert selection.news_reason({"title": "A new pizzeria", "stage": "coming_soon"})
    assert selection.news_reason({"title": "Bridge Bagels", "stage": "opened"}) is None


def test_kids_sections_required_fields_adult_wraparound_home_ed():
    ok = {"provider": "GK Fit", "title": "Multi-sport 9-12", "venue": "Cherry Hinton", "ages": "9-12", "category": "multi_sport"}
    assert selection.section_reason(ok) is None
    assert "возраст" in selection.section_reason(ok | {"ages": None, "title": "Kids"})
    assert "площадка" in selection.section_reason(ok | {"venue": None})
    assert selection.section_reason(ok | {"title": "Adult Fitness"}).startswith("взрослое")
    assert selection.section_reason(ok | {"title": "Cambridge Kestrels Senior Men Basketball"}).startswith("взрослое")
    assert selection.section_reason(ok | {"title": "Breakfast Club"}).startswith("продлёнка")
    assert selection.home_ed("Home Ed: Drop-off session")
    from pipeline.sections import school_hours
    assert school_hours({"days": "Monday", "hours": "12:40-13:40", "ages": "9-12"})
    assert not school_hours({"days": "Saturday", "hours": "10:00", "ages": "9-12"})


def test_programme_title_age_once_price_point_and_number_agreement():
    assert selection.dup_age("Cambridge Gymnastics (11-16 yrs) (11 to 16 yrs old)") == "Cambridge Gymnastics (11-16 yrs)"
    assert selection.fix_price_comma("£5,50 per session") == "£5.50 per session"
    assert selection.fix_price_comma("£1,200") == "£1,200"
    assert issue._n_ru(23, "программа", "программы", "программ") == "23 программы"
    assert issue._n_ru(21, "программа", "программы", "программ") == "21 программа"


def test_title_year_conflict():
    from tests.issue_rules.r51_title_year import year_conflict
    assert year_conflict("Wisbech Science Centre — School holidays (Oct 2027)", [("2026-10-26", "2026-10-30", None)])
    assert year_conflict("Cambridge Beer Festival 2027", [("2027-05-24", "2027-05-29", None)]) is None


def test_placeholders_leagues_stray_english():
    res = {"sections": [{"rubric": "kids", "items": [{"title_en": "X", "title_ru": "X", "where_ru": "TBC",
                                                      "price_ru": "N/A", "blurb_ru": "Занятие (not specified) для детей.",
                                                      "blurb_en": "A class (not specified)."}]}]}
    issue_fixes.fix_placeholders(res)
    it = res["sections"][0]["items"][0]
    assert it["where_ru"] == "" and it["price_ru"] == "цены на сайте" and "not specified" not in it["blurb_ru"]
    assert issue_fixes.league_fix("матч Лиги One") == "матч Первой лиги (League One)"
    assert issue_fixes.stray_english("Фильм о Greenland и уроки archery", "") == ["archery", "Greenland"]
    assert issue_fixes.stray_english("Концерт в Kettle's Yard", "Kettle's Yard") == []


def test_why_go_concrete_only():
    assert issue_fixes.why_problem({"why_ru": "Отличный способ провести вечер", "why_en": "A great way to spend an evening"})
    assert issue_fixes.why_problem({"why_ru": "Будет интересно", "why_en": "It will be interesting"}) == "нет конкретного факта"
    # этап 7h (правка 2 после v14): цена — не причина; часть с ценой убирается, факт остаётся
    assert issue_fixes.clean_why({"why_ru": "Бесплатно; подходит детям от 5 лет", "why_en": "Free; ages 5+"})[:2] == \
        ("Подходит детям от 5 лет.", "Ages 5+.")
    assert issue_fixes.why_problem({"why_ru": "Подходит детям от 5 лет.", "why_en": "Ages 5+."}) is None
    res = {"sections": [{"rubric": "weekdays", "items": [{"title_en": "X", "title_ru": "X", "why_ru": "Незабываемый вечер",
                                                          "why_en": "Unforgettable"}]}]}
    issue_fixes.fix_why_go(res, _pools({}))
    assert res["sections"][0]["items"][0]["why_ru"] == ""


def test_explain_and_translation():
    it = {"title_en": "Walking football", "title_ru": "Walking football", "blurb_ru": "Занятия walking football для всех.",
          "blurb_en": "Walking football sessions.", "ids": []}
    issue_fixes.fix_explain({"sections": [{"rubric": "sport", "items": [it]}]}, _pools({}))
    assert "без бега" in it["blurb_ru"]
    it2 = {"title_en": "Commercial dance", "title_ru": "Commercial dance", "blurb_en": "Commercial class",
           "blurb_ru": "Коммерческие мероприятия для подростков; cohousing и тренировки у сетки."}
    issue_fixes.fix_translation({"sections": [{"rubric": "kids", "items": [it2]}]})
    assert "стиле commercial" in it2["blurb_ru"] and "совместное проживание" in it2["blurb_ru"] and "крикетных" in it2["blurb_ru"]


def test_morris_explained_only_for_dance():
    it = {"title_en": "A Call to Art: William Morris", "title_ru": "A Call to Art: William Morris",
          "blurb_ru": "Выставка о William Morris и прерафаэлитах.", "blurb_en": "", "ids": []}
    issue_fixes.fix_explain({"sections": [{"rubric": "museums", "items": [it]}]}, _pools({}))
    assert "танец" not in it["blurb_ru"]


def test_event_types_and_editorial_bonus():
    kids = event_types.annotate({"kind": "event", "title": "Gruffalo trail", "kids_tag": True, "for_kids": True, "importance": 4})
    mus = event_types.annotate({"kind": "event", "title": "Frank Bowling exhibition", "venue": "Fitzwilliam Museum",
                                "long_running": True, "importance": 6})
    gig = event_types.annotate({"kind": "event", "title": "The Bluetones live", "importance": 6,
                                "categories": ["MusicEvent"]})
    comedy = event_types.annotate({"kind": "event", "title": "Nish Kumar: Angry Humour", "categories": ["ComedyEvent"],
                                   "importance": 7})
    assert kids["category"] == "kids" and kids["rank"] == 5.5
    assert mus["category"] == "museum" and mus["rank"] == 7.5
    assert gig["category"] == "concert" and gig["rank"] == 6
    assert comedy["category"] == "comedy"


def test_weekend_category_cap_and_subtype_diversity():
    import build_issue as b
    cands = {f"E{i}": {"kind": "event", "title": f"Gig {i}", "category": "concert", "rank": 10 - i, "event_ids": [i],
                       "dates": []} for i in range(4)}
    res = {"sections": [{"rubric": "weekend_1", "items": [{"ids": [k], "title_en": k, "title_ru": k} for k in cands]}]}
    b.cap_weekend_categories(res, _pools(cands), {})
    assert [it["ids"][0] for it in res["sections"][0]["items"]] == ["E0", "E1"]
    photo = {f"P{i}": {"kind": "event", "title": f"Photography talk {i}", "category": "talk", "rank": 5 - i, "event_ids": [10 + i],
                       "dates": []} for i in range(3)}
    res = {"sections": [{"rubric": "talks", "items": [{"ids": [k], "title_en": k, "title_ru": k} for k in photo]}]}
    b.diversity(res, _pools(photo), {})
    assert len(res["sections"][0]["items"]) == 2


def test_announce_lines_go_to_thematic_rubric():
    assert lines.announce_rubric({"types": ["racing"]}) == "sport"
    assert lines.announce_rubric({"types": ["family_hands_on"]}) == "kids"
    assert lines.announce_rubric({"types": ["concert"]}) == "weekdays"
    assert lines.announce_rubric({"types": ["museum_exhibition"]}) == "museums"


def test_festival_calendar_and_registry():
    ids = festivals.calendar_ids()
    assert {"R25", "R36", "R09"} <= ids and "R40" not in ids and "R50" not in ids   # Pride, Shakespeare; не Nine Lessons
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE recurring_events (rec_id TEXT, name TEXT, stage TEXT, stage_since TEXT, found_date TEXT,
                   found_date_end TEXT, expected_month TEXT, official_only TEXT, found_source TEXT, official_url TEXT)""")
    con.execute("INSERT INTO recurring_events VALUES ('R09','Folk','в продаже','2026-09-18','2027-07-30','2027-08-01','07',NULL,'вручную','u')")
    con.execute("INSERT INTO recurring_events VALUES ('R38','Jazz','ожидаем',NULL,NULL,NULL,'11','1',NULL,'u')")
    con.execute("INSERT INTO recurring_events VALUES ('R16','Mill Road','дата объявлена','2026-08-01','2026-12-05',NULL,'12',NULL,'x','u')")
    rows = {r["rec_id"]: r for r in con.execute("SELECT * FROM recurring_events")}
    assert festivals.due(rows["R09"], date(2026, 10, 15))[0]            # продажа открыта
    assert not festivals.due(rows["R38"], date(2026, 10, 15))[0]        # Jazz — только с сайта фестиваля
    assert festivals.due(rows["R16"], date(2026, 10, 15))[0]            # 7 недель до начала


def test_theme_history_eight_weeks_sent_only():
    con = sqlite3.connect(":memory:")
    history.init(con)
    history.record_theme(con, "2026-10-08", "v13", "Syd Barrett at 80", "Сиду Барретту — 80", [39])
    assert history.recent_themes(con, date(2026, 10, 15)) == []          # черновик не считается
    history.mark_sent(con, "2026-10-08", "v13")
    assert history.recent_themes(con, date(2026, 10, 15))[0]["event_ids"] == [39]
    assert history.recent_themes(con, date(2026, 12, 15)) == []          # через 8 недель — можно


def test_new_in_town_repeat_rule():
    con = sqlite3.connect(":memory:")
    history.init(con)
    res = {"sections": [{"rubric": "new_in_town", "items": [{"ids": ["V1"], "title_en": "Arbury Social"}]}]}
    history.record(con, "2026-10-08", "v13", res, {"V1": {"news_id": 1, "stage": "coming_soon", "title": "The Arbury Social"}})
    history.mark_sent(con, "2026-10-08", "v13")
    assert history.shown_places(con, date(2026, 10, 15)) == {"arbury social": {"coming_soon"}}


def test_editor_ratings_loader(tmp_path):
    from load_editor_ratings import load
    con = sqlite3.connect(":memory:")
    path = tmp_path / "r.json"
    path.write_text(json.dumps({"issue_date": "2026-10-08", "version": "v13",
                                "ratings": [{"id": "E818", "who": "editor", "rating": 2, "comment": "не событие?"},
                                            {"id": "K:x:1", "who": "wife", "rating": 1, "from_eid": "E700"}],
                                "rubrics": {"Бесплатно": {"rating": 0, "comment": "убрать"}}}, ensure_ascii=False))
    n = load(con, path, "2026-10-08", "v13")
    assert n["item"] == 2 and n["rubric"] == 1 and n["comments"] == 2
    assert con.execute("SELECT event_id FROM editor_ratings WHERE cand_id='E818'").fetchone()[0] == 818
    assert load(con, path, "2026-10-08", "v13")["item"] == 2   # повторная загрузка заменяет записи
    assert con.execute("SELECT count(*) FROM editor_ratings").fetchone()[0] == 3


def test_eventbrite_new_first_and_reserve():
    from collectors.generic import DetailCache

    class FakeHttp:
        requests = 0

        def __init__(self, left):
            self.left = left

        def day_left(self, host):
            return self.left

        def get(self, url):
            self.requests += 1

            class R:
                text = "<html></html>"
            return R()

    c = DetailCache()
    c.cache = {"https://www.eventbrite.co.uk/e/old-1": ("2026-01-01T00:00:00+00:00", {"title": "Old"})}
    assert c.order_links(["https://www.eventbrite.co.uk/e/old-1", "https://www.eventbrite.co.uk/e/new-2"])[0].endswith("new-2")
    c.start_details()
    http = FakeHttp(left=10)   # запас меньше REFRESH_RESERVE — старую страницу не перезапрашиваем
    assert c.detail(http, "https://www.eventbrite.co.uk/e/old-1") == {"title": "Old"} and http.requests == 0


def test_cus_org_blocked(tmp_path):
    from collectors import http as H
    c = H.PoliteClient.__new__(H.PoliteClient)
    c.db, c.stats, c.purpose = H.state(tmp_path / "s.db"), {"deferred": 0}, "test"
    try:
        c._check_host("cus.org", "https://cus.org/")
        raise AssertionError("cus.org должен быть закрыт")
    except H.Deferred:
        pass


def test_probation_404_root_is_not_closed(tmp_path, monkeypatch):
    """У ics.fixtur.es нет главной (404): после паузы домен открывается, а не уходит на паузу навсегда."""
    from collectors import http as H
    c = H.PoliteClient.__new__(H.PoliteClient)
    c.db, c.stats, c.purpose = H.state(tmp_path / "s.db"), {"deferred": 0, "network": 0}, "test"
    c.db.execute("INSERT INTO hosts(host, probation) VALUES ('ics.fixtur.es', 1)")
    monkeypatch.setattr(c, "allowed", lambda url: True)
    monkeypatch.setattr(c, "_network", lambda url, host, cond=None: H.Response(url, 404, b"Not found", {}))
    c._check_host("ics.fixtur.es", "https://ics.fixtur.es/v2/cambridge-united.ics")
    assert c.db.execute("SELECT probation FROM hosts WHERE host='ics.fixtur.es'").fetchone()[0] == 0


def test_holiday_programme_needs_place_and_age():
    """Строка каникулярной программы — с возрастом и местом; иначе «нужно дополнить» (в редакторской версии)."""
    base = {"kind": "programme", "verified": True, "audience": "eligible", "places": None, "zone": "центр",
            "title": "Half-Term Tennis Camp", "date_start": None, "dates": []}
    chosen, why = issue.holiday_selection(_pools({
        "ok": base | {"venue": "Cambridge LTC", "ages": "8 to 10 yrs old"},
        "noplace": base | {"venue": None, "address": None, "ages": "8 to 10 yrs old"},
        "noage": base | {"venue": "Cambridge LTC", "ages": "not specified"}}))
    assert chosen == ["ok"] and why["noplace"].startswith("нужно дополнить") and why["noage"].startswith("нужно дополнить")


def test_vague_provider_venue_not_inherited():
    """Площадку провайдера подставляем, только если она конкретная (не «multiple locations», не «selected pools»)."""
    assert issue.VAGUE_VENUE_RE.search("Multiple locations across Cambridge, Newmarket")
    assert issue.VAGUE_VENUE_RE.search("selected pools")
    assert not issue.VAGUE_VENUE_RE.search("The Little Gym") and not issue.VAGUE_VENUE_RE.search("Cambridge LTC")


def test_programme_ru_title_without_english():
    from pipeline import kids_collect
    con = sqlite3.connect(":memory:")
    con.execute(kids_collect.TEXT_CACHE)
    con.execute("INSERT INTO kids_text_cache VALUES ('p1', 'x', ?)",
                (json.dumps({"title_ru": "Раскрась тыкву (school holidays)"}, ensure_ascii=False),))
    assert kids_collect.text_of(con, "p1")["title_ru"] == "Раскрась тыкву"
    assert issue._ages("11 to 16 yrs old", "ru") == "11–16 лет"
