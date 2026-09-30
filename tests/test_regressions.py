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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
