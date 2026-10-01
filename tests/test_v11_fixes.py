"""Этап 7e: регрессионные тесты правок по v11 (без сети и API)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pipeline import issue, issue_fixes  # noqa: E402


def _pools(cands: dict) -> issue.Pools:
    p = issue.Pools()
    p.candidates = cands
    return p


def test_price_from_same_event_olly_murs():
    import build_issue as b
    p = _pools({"T8": {"kind": "tickets", "title": "Olly Murs", "dates": [("2027-06-25", "2027-06-25", None)],
                       "event_ids": [1964], "price_text": None, "price_from": None},
                "A909": {"kind": "announcement", "title": "Olly Murs at Newmarket Nights",
                         "dates": [("2027-06-25", "2027-06-25", None)], "event_ids": [909], "price_text": "from £45",
                         "price_from": 45.0}})
    it = {"title_en": "Olly Murs", "title_ru": "Olly Murs", "price_en": "£45", "price_ru": "£45"}
    assert b.check_price(it, [p.candidates["T8"]], b.same_event(p, ["T8"])) is None and it["price_ru"] == "£45"
    it = {"title_en": "Olly Murs", "title_ru": "Olly Murs", "price_en": "£40", "price_ru": "£40"}
    assert b.check_price(it, [p.candidates["T8"]], b.same_event(p, ["T8"])) and it["price_ru"] == "£45"


def test_original_title_pooh():
    p = _pools({"E1": {"kind": "event", "title": "Three Cheers for Pooh! Story trail", "event_ids": [1], "dates": []}})
    res = {"sections": [{"rubric": "kids", "items": [{"ids": ["E1"], "title_en": "Three Cheers for Pooh! Story trail",
                                                      "title_ru": "Три ура Винни-Пуху! Сказочная тропа"}]}]}
    assert issue_fixes.fix_original_titles(res, p)
    assert res["sections"][0]["items"][0]["title_ru"] == "Three Cheers for Pooh! Story trail"


def test_father_christmas_not_ded_moroz():
    p = _pools({"E1": {"kind": "event", "title": "Meet Father Christmas", "event_ids": [1], "dates": []}})
    it = {"ids": ["E1"], "title_en": "Meet Father Christmas", "title_ru": "Встреча с Дедом Морозом",
          "blurb_ru": "Дед Мороз ждёт детей в гроте."}
    issue_fixes.fix_realia({"sections": [{"rubric": "kids", "items": [it]}]}, p)
    assert "Мороз" not in it["title_ru"] + it["blurb_ru"] and "Сантой" in it["title_ru"]


def test_support_act_not_in_source():
    p = _pools({"E39": {"kind": "event", "title": "A Tribute to Syd Barrett", "event_ids": [39], "dates": [],
                        "summary": "With Kula Shaker and Soft Machine, light show by The Mad Alchemist"}})
    res = {"sections": [{"rubric": "theme", "items": [{"ids": ["E39"], "title_en": "x", "title_ru": "x",
                                                       "blurb_en": "Kula Shaker headline, with Soft Machine in support.",
                                                       "blurb_ru": "Хедлайнеры — Kula Shaker, на разогреве Soft Machine."}]}]}
    assert issue_fixes.unsupported_roles(res, p)
    p.candidates["E39"]["summary"] += "; support from Soft Machine"
    assert not issue_fixes.unsupported_roles(res, p)


def test_news_town_in_title():
    c = {"kind": "venue_news", "title": "David Lloyd St Neots", "address": "Nuffield Road, Wintringham, St Neots"}
    assert issue.news_town(c) == "St Neots" and issue.TOWN_RU["St Neots"] == "Сент-Нитс"
