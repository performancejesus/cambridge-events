"""Этап 7h: регрессионные тесты правок после чтения v14 (12.10), пункты 1–12 (без сети и API)."""

from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pipeline import broadcast, issue, issue_fixes, page_times, selection  # noqa: E402
from pipeline.glossary import hockey_ru  # noqa: E402

W = issue.Window(date(2026, 10, 15), date(2026, 10, 15), date(2026, 10, 25))


def _pools(cands: dict) -> issue.Pools:
    p = issue.Pools()
    p.candidates = cands
    return p


# 1. пояснение не к имени; находка «не по контексту» — блокирующая (проверка 63)
def test_morris_name_not_explained():
    it = {"title_en": "A Call to Art", "title_ru": "A Call to Art", "ids": ["E1"],
          "blurb_ru": "Дизайны, ткани и живопись Уильяма Морриса и прерафаэлитов."}
    p = _pools({"E1": {"title": "A Call to Art: William Morris and the Pre-Raphaelites", "summary": ""}})
    issue_fixes.fix_explain({"sections": [{"rubric": "theme", "items": [it]}]}, p)
    assert "танец" not in it["blurb_ru"]
    dance = {"title_en": "Ely Morris", "title_ru": "Ely Morris", "ids": ["E2"], "blurb_ru": "Выступают команды моррис."}
    issue_fixes.fix_explain({"sections": [{"rubric": "kids", "items": [dance]}]},
                            _pools({"E2": {"title": "Morris dancing on the green", "summary": ""}}))
    assert "народный танец" in dance["blurb_ru"]


def test_wrong_explanation_removed_and_blocked():
    it = {"title_en": "A Call to Art", "title_ru": "A Call to Art", "ids": ["E1"],
          "blurb_ru": "Живопись Морриса (английский народный танец) из коллекции музея."}
    p = _pools({"E1": {"title": "A Call to Art: William Morris", "summary": ""}})
    assert issue_fixes.wrong_explanations(it, "A Call to Art: William Morris") == ["английский народный танец"]
    issue_fixes.fix_explain({"sections": [{"rubric": "theme", "items": [it]}]}, p)
    assert "танец" not in it["blurb_ru"]
    from tests.issue_rules import BLOCK
    from tests.issue_rules import r63_explain_context as r63
    assert r63.LEVEL == BLOCK
    # находка сверки ушла в «Факты из знаний модели» — всё равно нарушение
    it2 = {"blurb_ru": "Живопись Морриса.", "knowledge_ru": ["Моррис упоминается как английский народный танец"]}
    assert issue_fixes.wrong_explanations(it2, "William Morris")


# 2. «Почему стоит пойти»: цена и дата — не причина; «бесплатно» при платной цене — противоречие
def test_why_price_date_only():
    cases = [("Бесплатный вход.", "Free entry.", "бесплатно"), ("Открывается 23 октября.", "Opens 23 October.", "от £16"),
             ("Бесплатно, работает до марта 2027 года.", "Free, runs to March 2027.", "бесплатно"),
             ("Открывается 20 октября, вход бесплатный.", "Opens 20 October, free.", "бесплатно")]
    for ru, en, price in cases:
        assert issue_fixes.clean_why({"why_ru": ru, "why_en": en, "price_ru": price})[0] == "", ru
    ru, en, note = issue_fixes.clean_why({"why_ru": "Бесплатно; пять десятилетий работы одного фотографа.",
                                         "why_en": "Free; five decades of one photographer's work.", "price_ru": "бесплатно"})
    assert ru == "Пять десятилетий работы одного фотографа." and en.startswith("Five decades")
    ru, _, note = issue_fixes.clean_why({"why_ru": "Бесплатно, работает до 1 ноября.", "why_en": "Free, runs to 1 November.",
                                        "price_ru": "цены на сайте"})
    assert ru == "" and note == "противоречит строке цены"


def test_fix_why_go_trims():
    it = {"title_en": "X", "title_ru": "X", "why_ru": "Бесплатно; подходит для посетителей от 12 лет.",
          "why_en": "Free; suits visitors from age 12.", "price_ru": "бесплатно"}
    issue_fixes.fix_why_go({"sections": [{"rubric": "museums", "items": [it]}]}, _pools({}))
    assert it["why_ru"] == "Подходит для посетителей от 12 лет."


# 3. запятые в ценах — во всём выпуске
def test_price_comma_everywhere():
    assert issue.polish_text("£43–£45,20 · £18,50 · £1,200") == "£43–£45.20 · £18.50 · £1,200"
    out = issue.polish_layout({"intro": "от £7,70", "sections": [{"intro": "", "groups": [{"items": [
        {"title": "X", "meta": "£18,50", "blurb": "билеты £13,80", "why": ""}]}]}]})
    it = out["sections"][0]["groups"][0]["items"][0]
    assert out["intro"] == "от £7.70" and it["meta"] == "£18.50" and it["blurb"] == "билеты £13.80"


# 4. провайдер — владелец страницы, а не организация, названная в тексте
def test_provider_is_page_owner():
    orgs = {"cambridgeppf.org": "Cambridge Past, Present & Future", "botanic.cam.ac.uk": "Cambridge University Botanic Garden",
            "pitchgurus.co": "University of Cambridge", "childcare.admin.cam.ac.uk": "Childcare Services"}
    assert issue.provider_name("Cambridge University Botanic Garden/Wandlebury Country Park", "cambridgeppf.org", orgs) == \
        "Cambridge Past, Present & Future"
    assert issue.provider_name("University of Cambridge Holiday Playscheme", "childcare.admin.cam.ac.uk", orgs) == \
        "University of Cambridge Holiday Playscheme"
    assert issue.provider_name("Cambridge LTC", "cambridgeltc.com", orgs) == "Cambridge LTC"


# 5. трансляции: труппа по префиксу серии
def test_broadcast_series():
    t = "RBO 26-27: Macbeth (MET Opera)"
    assert broadcast.series_of(t) == "rbo" and broadcast.clean_title(t) == "RBO 26-27: Macbeth"
    assert broadcast.clean_title("The MET 26/27 - Otello") == "The MET 26/27 - Otello"
    assert broadcast.clean_title("Macbeth (Met Opera)", broadcast.series_of(t)) == "Macbeth"   # пункт модели без префикса
    txt = "Трансляция оперы Верди «Макбет» из нью-йоркской Metropolitan Opera — часть серии MET Opera."
    fixed = broadcast.fix_text(t, txt, "ru")
    assert "Metropolitan" not in fixed and "MET" not in fixed and "Royal Ballet and Opera (Лондон)" in fixed
    assert broadcast.wrong_mentions(t, txt) and not broadcast.wrong_mentions(t, fixed)


# 6. время — со страницы события; «вечерний показ» и дневное время — противоречие
def test_page_time():
    text = "Saturday 24th October 2026 | 4:00 PM – 9:00 PM | The drone show will begin approximately 30 minutes after " \
           "sunset and is currently expected to start between 7:15 PM and 8:00 PM, subject to change."
    pt = page_times.page_time(text)
    assert pt == {"start": "16:00", "end": "21:00", "show_from": "19:15", "show_to": "20:00"}
    c = {"kind": "event", "dates": [("2026-10-24", "2026-10-24", "12:00"), ("2026-10-24", "2026-10-24", "16:00")]}
    assert page_times.apply(c, pt, text) and c["dates"] == [("2026-10-24", "2026-10-24", "16:00")]
    assert issue.when(c | {"title": "x"}, W, "ru") == "сб, 24 октября, с 16:00, шоу около 19:15–20:00"
    # время из списка есть на странице — не трогаем
    c2 = {"kind": "event", "dates": [("2026-10-20", "2026-10-20", "19:30")]}
    assert not page_times.apply(c2, page_times.page_time("Doors 7pm | 10:00 am – 5:00 pm box office"), "Tue 20 Oct, 7:30pm")
    assert page_times.SHOWS_RU.sub("", "рассказ телеведущей — два вечерних показа.") == "рассказ телеведущей."
    assert page_times.SHOWS_EN.sub("", "narrated by a TV presenter, in two evening shows.") == "narrated by a TV presenter."
    from tests.issue_rules.r65_time_context import EVENING_RU
    assert EVENING_RU.search("два вечерних показа")


# 7. регулярная экскурсия: одно название на одной площадке, 4+ даты за месяц, страницы разные
def test_series_regular():
    assert selection.series_regular(["2026-10-03", "2026-10-10", "2026-10-17", "2026-10-24"])
    assert not selection.series_regular(["2026-10-10", "2026-10-24", "2026-11-07"])
    urls = ["https://www.kettlesyard.cam.ac.uk/whats-on/guided-house-tour-24-10-2026/",
            "https://www.museums.cam.ac.uk/events/guided-house-tour-27", "https://www.museums.cam.ac.uk/events/guided-house-tour-28"]
    assert selection.series_regular(["2026-10-24", "2026-11-07", "2026-11-21"], urls)
    assert issue.SERIES_EXEMPT_RE.search("Hadestown: The Musical") and issue.SERIES_EXEMPT_RE.search("ECMS Lunchtime Recital")


# 8. фестиваль идёт в окне — кандидат в «Главное» при любой оценке, без строки календаря
def test_running_festival():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE recurring_events (rec_id, name, event_id, found_date, found_date_end)")
    con.execute("INSERT INTO recurring_events VALUES ('R17', 'Cambridge Film Festival', 2266, '2026-10-22', '2026-11-01')")
    p = _pools({"E906": {"kind": "event", "title": "Cambridge Film Festival 2026", "event_ids": [906], "long_running": True,
                         "on_weekends": ["weekend_2"], "rank": 3.0, "importance": 3.0, "zone": "центр"}})
    assert issue.running_festivals(con, W, p) == {"R17": "E906"}
    c = p.candidates["E906"]
    assert c["festival_running"] and "long_running" not in c
    import build_issue
    assert build_issue.fits("weekend_2", c, W)


# 9. зона и год один раз, без названий источников, «хоккей на траве»
def test_polish_and_hockey():
    assert issue.polish_text("до 1 ноября · Wimpole Estate (до 30 мин) · до 30 мин · по билету") == \
        "до 1 ноября · Wimpole Estate (до 30 мин) · по билету"
    assert issue.polish_text("15 января 2027 – 17 января 2027") == "15–17 января 2027"
    assert issue.polish_text("30 июля 2027 – 1 августа 2027 · Кембридж") == "30 июля – 1 августа 2027 · Кембридж"
    assert issue.polish_text("в продаже с 18 сентября (Cambridge Independent)") == "в продаже с 18 сентября"
    assert hockey_ru("Cambridge South Hockey Club: Хоккей, 11–12 лет", "U12 Girls Junior Hockey") == \
        "Cambridge South Hockey Club: Хоккей на траве, 11–12 лет"
    assert hockey_ru("Хоккей", "Peterborough Phantoms ice hockey") == "Хоккей"


# 10. мероприятие школы для своих — по правилу дней открытых дверей
def test_school_event():
    page = "Parent/Carer coaching workshop | M | By | Milton Road Primary School | Organized by | M | Milton Road Primary School"
    assert selection.school_event_reason("Parent/Carer coaching workshop", "Milton Road Primary School", page)
    assert not selection.school_event_reason("Durga Puja 2026", "The Netherhall School", "Organized by | Indian Cultural Society")
    assert not selection.school_event_reason("Parent workshop", "Cambridge Central Library", page)


# 11. каникулярная неделя — сезонный вариант темы
def test_seasonal_theme_option():
    import build_issue
    assert build_issue.holiday_week(W) == "october_half_term"
    cands = {f"E{i}": {"kind": "event", "title": t, "zone": "центр", "on_weekends": ["weekend_2"], "rank": 5 - i * 0.1,
                       "event_ids": [i]}
             for i, t in enumerate(["Halloween Trail", "Pumpkin Festival", "Spooky Story Time", "Half-term Science Fun",
                                    "Ghost Walk"])}
    res = {"theme_options": [{"title_en": "Fitzwilliam", "ids": ["E99"]}], "sections": []}
    notes = build_issue.seasonal_theme_option(res, _pools(cands), W)
    assert notes and res["theme_options"][-1]["title_ru"] == "Хэллоуин и школьные каникулы"
    assert len(res["theme_options"][-1]["ids"]) == 5
    assert build_issue.seasonal_theme_option(res, _pools(cands), W) == []   # уже есть — второй раз не добавляем
    assert build_issue.holiday_week(issue.Window(date(2026, 9, 10), date(2026, 9, 10), date(2026, 9, 20))) is None


# 12. «Главное» меньше 10 — редактору объяснено почему
def test_weekend_shortfall():
    import build_issue
    mk = lambda i, cat: {"kind": "event", "title": f"T{i}", "category": cat, "on_weekends": ["weekend_1"], "rank": 6.0,
                         "importance": 6.0, "zone": "центр", "event_ids": [i]}
    cands = {f"E{i}": mk(i, "comedy") for i in range(5)} | {"E9": mk(9, "museum")}
    res = {"sections": [{"rubric": "weekend_1", "items": [{"ids": ["E0"]}, {"ids": ["E1"]}]},
                        {"rubric": "museums", "items": [{"ids": ["E9"]}]}]}
    why = build_issue.weekend_shortfall(res, _pools(cands), W)
    ru = why["weekend_1"]["ru"]
    assert ru.startswith("2 из 10") and "1 стоят в других рубриках" in ru and "комедия (ещё 3)" in ru


# разметка v13 → правила 7h: встречи с авторами — «Лекции и встречи», дегустации — не «Научиться», «Новое в городе»,
# «Cut Your Own» — не музей, «руленые бейглы»
def test_markup_rules():
    assert issue.MEETING_RE.search("An Evening with Colette Paul in Cambridge") and issue.MEETING_RE.search("Poetry + Pints")
    assert issue.MEETING_RE.search("The Little Review: A Literary Salon") and issue.BOOKSHOP_RE.search("Heffers Bookshop")
    from pipeline.courses import LEARN_RE, NOT_LEARN_RE
    t = "Childhood Charcuterie: A Nostalgic Wine & Snack Tasting Experience"
    assert not (LEARN_RE.search(t) and not NOT_LEARN_RE.search(t))
    assert LEARN_RE.search("Creative Comics Drawing evening at Hot Numbers")
    assert selection.news_reason({"title": "New pizza restaurant (unnamed)"})
    assert selection.news_reason({"title": "Lake View Bereavement Centre"})
    import build_issue
    assert not build_issue.fits("museums", {"kind": "event", "title": "Cut Your Own Dahlias", "long_running": True}, W)
    it = {"title_en": "Bridge Bagels", "title_ru": "Bridge Bagels", "blurb_ru": "Руленые бейглы в нью-йоркском стиле."}
    issue_fixes.fix_translation({"sections": [{"rubric": "new_in_town", "items": [it]}]})
    assert "ручной формовки" in it["blurb_ru"]


def test_first_season_not_superlative():
    """Блок v14b: «horses in their first season» — не «впервые»; «first time» в том же тексте — по-прежнему «впервые»."""
    from tests.issue_rules.r01_verified_facts import classify
    assert "super" not in classify("Racing for horses in their first season, as the juvenile division winds down.")
    assert "super" in classify("The first time the show comes to Cambridge.")
    assert "super" in classify("Впервые в Кембридже — первый сезон.")
