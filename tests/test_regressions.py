"""Постоянные регрессионные тесты обязательных проверок (этап 7c). Запуск: python -m pytest tests -q
(или python tests/test_regressions.py). Не удалять без решения редактора."""

from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import issue, verified_facts  # noqa: E402
from tests.issue_rules import r01_verified_facts, r18_duplicate_names, r19_titles, r30_football_league  # noqa: E402
from tests.issue_rules.common import Ctx, name_in_text  # noqa: E402


def _ctx(result: dict, issue_date=date(2026, 10, 8)) -> Ctx:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    verified_facts.init(con)
    w = issue.Window(issue_date, issue_date, issue_date.replace(day=issue_date.day + 10))
    return Ctx(w=w, version="test", result=result, pools=issue.Pools(), con=con, out_dir=ROOT / "issues", stem="test")


def _result(intro_ru="", intro_en="", items=()):
    return {"intro_ru": intro_ru, "intro_en": intro_en, "theme_intro_ru": "", "theme_intro_en": "",
            "sections": [{"rubric": "theme", "items": list(items)}]}


def test_barrett_this_month_blocks():
    """Syd Barrett родился 6 января 1946: «в этом месяце исполнилось бы 80» в выпуске октября — ошибка (v5, v9)."""
    ctx = _ctx(_result("Сиду Барретту в этом месяце исполнилось бы 80 лет.",
                       "Syd Barrett would have turned 80 this month."))
    f = r01_verified_facts.check(ctx)
    assert any("в этом месяце" in v and "06.01.1946" in v for v in f.violations), f.violations
    assert len(f.violations) >= 2   # и русский, и английский текст


def test_barrett_this_year_passes():
    ctx = _ctx(_result("В этом году Сиду Барретту исполнилось бы 80 лет.", "Syd Barrett would have turned 80 this year."))
    assert not r01_verified_facts.check(ctx).violations


def test_barrett_wrong_age_blocks():
    ctx = _ctx(_result("Сиду Барретту исполнилось бы 81 год.", ""))
    assert r01_verified_facts.check(ctx).violations


def test_unknown_birthday_blocks():
    ctx = _ctx(_result("Композитору в этом месяце исполнилось бы 90 лет.", ""))
    assert r01_verified_facts.check(ctx).violations


def test_duplicate_name_in_cyrillic():
    """«Также в программе: Professor Josephine Crawley Quinn», когда она уже названа кириллицей (v9)."""
    assert name_in_text("Professor Josephine Crawley Quinn", "Профессор Джозефин Кроули Куинн читает лекцию")
    assert name_in_text("Rob Chapman", "Лекция Роба Чапмена")
    assert not name_in_text("Kula Shaker", "Soft Machine и другие")
    it = {"ids": [], "title_ru": "Anarchical Antiquity", "title_en": "Anarchical Antiquity",
          "blurb_ru": "Профессор Джозефин Кроули Куинн читает лекцию. Также в программе: Professor Josephine Crawley Quinn.",
          "blurb_en": "Professor Josephine Crawley Quinn gives a lecture."}
    ctx = _ctx({"sections": [{"rubric": "talks", "items": [it]}]})
    assert r18_duplicate_names.check(ctx).violations


def test_title_tails():
    assert r19_titles.strip_tail("Simply Red на ипподроме Ньюмаркета — билеты уже в продаже") == "Simply Red на ипподроме Ньюмаркета"
    assert r19_titles.strip_tail("Fireworks Night — 5 ноября") == "Fireworks Night"
    assert r19_titles.strip_tail("A Tribute to Syd Barrett: 80-летие") == "A Tribute to Syd Barrett: 80-летие"
    assert r19_titles.strip_tail("Sunil Gupta: Life with a Camera, 1970 – Now") == "Sunil Gupta: Life with a Camera, 1970 – Now"


def test_league_two_not_confirmed():
    """«Матч Лиги Two» у Cambridge United — лига из знаний модели; по сайту клуба в 2026/27 — League One."""
    ctx = _ctx({"sections": []})
    cands = [{"title": "Cambridge United FC - Blackpool FC", "sources": ["S018"], "summary": None, "categories": ["football"]}]
    assert not r30_football_league.confirmed(ctx, cands, "Обычный матч Лиги Two")
    assert r30_football_league.confirmed(ctx, cands, "Матч League One")


# --- этап 7d: правки по v10 ---

def test_film_names_latin():
    """«В кино» v10: «Пол Гринграсс», «Томасин Маккензи», «Джо Кой» — имена из описания Wikipedia — кириллицей."""
    from tests.issue_rules.r09_latin_names import cyrillic_only, names_of
    film = {"kind": "film_release", "title": "The Uprising",
            "wiki_extract": "The Uprising is a 2026 film directed by Paul Greengrass, starring Andrew Garfield and "
                            "Thomasin McKenzie. Voice cast includes Jo Koy."}
    names = names_of([film])
    text = "Пол Гринграсс поставил фильм; Andrew Garfield и Томасин Маккензи; среди голосов — Джо Кой."
    bad = {n for n in names if cyrillic_only(n, text)}
    assert bad == {"Paul Greengrass", "Thomasin McKenzie", "Jo Koy"}


def test_opening_stage_conflict():
    """Bridge Bagels v10: «Открылось 28 сентября», а в описании — «скоро откроется»."""
    from pipeline.issue_fixes import stage_conflict
    c = {"kind": "venue_news", "stage": "opened", "date": "2026-09-28", "date_basis": "stated"}
    it = {"blurb_ru": "В Кембридже скоро откроется пекарня бейглов.", "blurb_en": "A bagel bakery is opening soon."}
    assert stage_conflict(c, it)
    assert not stage_conflict(c, {"blurb_ru": "Пекарня бейглов открылась на Bridge Street.", "blurb_en": ""})
    w = issue.Window(date(2026, 10, 8), date(2026, 10, 8), date(2026, 10, 18))
    soon = {"kind": "venue_news", "stage": "coming_soon", "date": "2026-09-28", "date_basis": "stated"}
    assert issue.when(soon, w, "ru") == "Скоро откроется"   # прошедшая дата — не дата открытия


def test_festival_reminder_and_announcement():
    """Ежегодные фестивали: напоминание за 4–6 недель, анонс — при новой стадии, иначе не повторяем."""
    w = issue.Window(date(2026, 10, 8), date(2026, 10, 8), date(2026, 10, 18))
    row = lambda start, stage, since: {"date_start": start, "stage": stage, "stage_since": since}
    assert issue.festival_stage(row("2026-11-05", "дата объявлена", "2026-08-01"), w)[0] == "reminder"
    assert issue.festival_stage(row("2026-12-05", "дата объявлена", "2026-09-27T18:00"), w)[0] == "announced"
    assert issue.festival_stage(row("2026-12-05", "в продаже", "2026-10-01"), w)[0] == "on_sale"
    assert issue.festival_stage(row("2026-12-05", "дата объявлена", "2026-08-01"), w) is None


def test_recurring_town_and_shared_page():
    """7c: «Cambridge Christmas lights switch-on» совпало с огнями Висбеча; Stourbridge Fair взял дату «Гамлета»."""
    import re
    from pipeline.recurring import dates_near, in_town
    wisbech = {"title": "CHRISTMAS LIGHTS SWITCH ON", "venue_name": None, "address": None, "zone": "Кембриджшир, дальше часа",
               "url": "https://www.wisbechtowncouncil.gov.uk/local-events?month=2026-11"}
    assert not in_town(wisbech, "Cambridge")
    page = ("attend September 30, 2026 Leper Chapel. Hamlet by in situ: Wednesday 30 Sep. " + "x " * 400 +
            "Stourbridge Fair which was the largest fair in Europe at one point")
    rx = re.compile("Stourbridge Fair", re.I)
    assert dates_near(page, rx, {"09"}, "2026-09-01") == []


def test_mlc_slug_tokens():
    from pipeline.ingest import _slug_tokens
    assert "beat" in _slug_tokens("https://musiclivecambridge.com/events/the-beat-the-selecter/")
    assert "cambridge" not in _slug_tokens("https://x/the-beat-cambridge/")


def test_price_year_not_a_price():
    """v11: «£8 2026 PYO Season Ticket» (Bury Lane) давало «£2–£2026»."""
    assert issue.price_from_data({"price_text": "£2 day ticket (under 5s free) or £8 2026 PYO Season Ticket",
                                  "price_from": 2.0}) == ("£2–£8", "£2–£8")


def test_museum_line_kinds():
    """v11: сезонный сбор цветов и семейные занятия на много недель — не «выставка»."""
    from pipeline.museums import kind_of
    assert kind_of({"title": "Cut Your Own Dahlias", "categories": ["farm", "exhibition"], "long_running": True}) == "seasonal"
    assert kind_of({"title": "Mucky Pups", "categories": ["family"], "long_running": True}) == "family"
    assert kind_of({"title": "Guided House Tour", "long_running": True}) == "tour"
    assert kind_of({"title": "Susan Tomes, piano"}) == "concert"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
