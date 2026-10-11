"""Этап 7g: компактные строки без модели — «Объявлено: …», «Волонтёрство», parkrun.

- «Объявлено: …» (вместо рубрики «Новые анонсы», решено 11.10): анонсы (A…) и старты продаж без срочности (T…) идут в
  конец тематической рубрики короткими строками, 1–3 на рубрику: скачки и забеги — «Спорт», концерты, театр и комедия —
  «На неделе», детское — «С детьми», выставки — «Музеи, выставки и усадьбы», лекции — «Лекции и встречи», фестивали —
  «Фестивали». Обязательные ежегодные события (Cambridge Half Marathon 2027 и т. п.) — первыми.
- «Волонтёрство» (новая рубрика): рабочие выезды, уборки, посадки деревьев (тэг volunteering) — строками с датой и
  местом; источники — CPPF, Wildlife Trust BCN, National Trust, уборки реки Cam, Cambridge CVS.
- parkrun (правила отбора 11.10): одна строка без даты окончания со ссылкой на parkrun.org.uk — взрослый (5 км,
  каждую субботу в 9:00) в «Спорт: поучаствовать», junior (2 км, 4–14 лет, каждое воскресенье) в «Секции» детской
  рубрики. Отдельные забеги parkrun в выпуск не идут.
"""

from __future__ import annotations

import re

from . import festivals

ANNOUNCE_MAX = 3
VOLUNTEER_MAX = 6
PARKRUN_URL = "https://www.parkrun.org.uk/"
PARKRUN_RE = re.compile(r"\bparkrun\b", re.I)


def announce_rubric(c: dict) -> str:
    t = set(c.get("types") or [])
    if t & {"racing", "local_sport"} or c.get("participant"):
        return "sport"
    if "family_hands_on" in t:
        return "kids"
    if "festival" in t:
        return "festivals"
    if t & {"museum_exhibition", "museum_talk"}:
        return "museums"
    if c.get("talk") or "academic_seminar" in t:
        return "talks"
    return "weekdays"


def _placed(result: dict, pools) -> set[int]:
    return {e for sec in result["sections"] for it in sec["items"] for i in it["ids"]
            for e in (pools.candidates.get(i) or {}).get("event_ids", [])}


def _empty(**kw) -> dict:
    return {"where_en": "", "where_ru": "", "price_en": "", "price_ru": "", "blurb_en": "", "blurb_ru": "",
            "knowledge_en": [], "knowledge_ru": [], "why_en": "", "why_ru": "", "line": True} | kw


def announce_items(pools, result: dict, w) -> dict[str, list[dict]]:
    """Рубрика → строки «Объявлено: …» (не больше ANNOUNCE_MAX; обязательные ежегодные — первыми и в счёт)."""
    from .issue import price_from_data, when
    placed = _placed(result, pools)
    from .normalize import norm_title
    placed_urls = {pools.candidates[i].get("url") for sec in result["sections"] for it in sec["items"] for i in it["ids"]
                   if i in pools.candidates and pools.candidates[i].get("url")}
    placed_titles = {norm_title(pools.candidates[i]["title"]) for sec in result["sections"] for it in sec["items"]
                     for i in it["ids"] if i in pools.candidates and pools.candidates[i].get("title")}
    # «Куда сходить с детьми в каникулы» собирается при вёрстке — его события тоже уже в выпуске
    placed_titles |= {norm_title(c["title"]) for c in pools.candidates.values() if c["kind"] == "holiday_event"}
    by_rub: dict[str, list[tuple]] = {}
    for cid, c in pools.candidates.items():
        if c["kind"] not in ("announcement", "tickets") or c.get("urgency") or not c.get("event_ids"):
            continue
        if set(c["event_ids"]) & placed or (c.get("url") and c["url"] in placed_urls) or \
                norm_title(c["title"]) in placed_titles:
            continue   # то же шоу уже стоит карточкой (The Gruffalo в окне и его поздние даты) — без «Объявлено»
        fest = c.get("festival") or {}
        if fest.get("rec_id") and fest["rec_id"] in festivals.calendar_ids():
            continue   # фестивали и ярмарки из реестра — календарь «Фестивали»
        mandatory = "ежегодного" in (c.get("evidence") or "")
        by_rub.setdefault(announce_rubric(c), []).append((not mandatory, -(c.get("rank") or c.get("importance") or 0), cid))
    out: dict[str, list[dict]] = {}
    for rub, lst in by_rub.items():
        seen_ev = set()
        for _, _, cid in sorted(lst):
            c = pools.candidates[cid]
            if set(c["event_ids"]) & seen_ev or len(out.get(rub, [])) >= ANNOUNCE_MAX:
                continue
            seen_ev |= set(c["event_ids"])
            st = ("tickets on sale", "билеты в продаже") if c["kind"] == "tickets" or c.get("status") == "on_sale" else \
                ("date announced", "дата объявлена")
            en, ru = price_from_data(c)
            meta = {lang: " · ".join(x for x in (when(c, w, lang), c.get("venue") or "", st[i],
                                                 "" if (en if lang == "en" else ru) in ("price not listed", "цена не указана")
                                                 else (en if lang == "en" else ru)) if x)
                    for i, lang in enumerate(("en", "ru"))}
            # заголовок группы — «Объявлено»; в строке — название события в оригинале
            out.setdefault(rub, []).append(_empty(ids=[cid], title_en=c["title"], title_ru=c["title"], meta_en=meta["en"],
                                                  meta_ru=meta["ru"], url=c.get("url"), announce_line=True))
    return out


def volunteer_items(pools, result: dict, w) -> tuple[list[dict], dict[str, str]]:
    from .issue import when
    placed = _placed(result, pools)
    cands = sorted(((cid, c) for cid, c in pools.candidates.items()
                    if c["kind"] == "event" and "volunteering" in (c.get("types") or [])),
                   key=lambda x: x[1]["dates"][0][0] if x[1].get("dates") else "9999")
    items, why = [], {}
    for cid, c in cands:
        if set(c["event_ids"]) & placed:
            why[cid] = "уже в выпуске"
            continue
        if len(items) >= VOLUNTEER_MAX:
            why[cid] = f"лимит рубрики ({VOLUNTEER_MAX} строк)"
            continue
        place = c.get("venue") or ", ".join((c.get("address") or "").split(",")[:2])
        meta = {lang: " · ".join(x for x in (when(c, w, lang), place,
                                             ("free" if lang == "en" else "бесплатно") if c.get("free_tag") else "") if x)
                for lang in ("en", "ru")}
        items.append(_empty(ids=[cid], title_en=c["title"], title_ru=c["title"], meta_en=meta["en"], meta_ru=meta["ru"],
                            url=c.get("url"), volunteer_line=True))
        why[cid] = "в выпуске"
    return items + standing_volunteer_items(), why


# постоянные строки «Волонтёрства» (проверены на сайтах 11.10): база вакансий и волонтёрские уборки — всегда в конце
STANDING_VOLUNTEER = [
    {"title_en": "Volunteer Cambs — volunteering opportunities across Cambridgeshire",
     "title_ru": "Volunteer Cambs — база волонтёрских вакансий Кембриджшира",
     "meta_en": "Support Cambridgeshire (Cambridge CVS) · regular and one-off roles",
     "meta_ru": "Support Cambridgeshire (Cambridge CVS) · постоянная и разовая помощь",
     "url": "https://cambridgecvs.org.uk/volunteering/volunteer-cambs"},
    {"title_en": "Litter picking with Cambridge City Council", "title_ru": "Уборка мусора с Cambridge City Council",
     "meta_en": "on your own or as a local group · the council lends equipment",
     "meta_ru": "в одиночку или своей группой · инструменты даёт городской совет",
     "url": "https://www.cambridge.gov.uk/volunteer-litter-picking"},
]


def standing_volunteer_items() -> list[dict]:
    return [_empty(ids=[f"X:volunteer{n}"], volunteer_line=True, standing=True, **x) for n, x in enumerate(STANDING_VOLUNTEER, 1)]


def parkrun_items() -> dict[str, dict]:
    """Строки parkrun: «sport» (взрослый) и «kids» (junior)."""
    return {
        "sport": _empty(ids=["X:parkrun"], title_en="parkrun — free 5 km run", title_ru="parkrun — бесплатный забег на 5 км",
                        meta_en="every Saturday at 9:00 · parks in Cambridge and around · register once, free",
                        meta_ru="каждую субботу в 9:00 · парки Кембриджа и округи · бесплатно, один раз "
                                "зарегистрироваться на сайте",
                        kind_en="parkrun", kind_ru="parkrun — еженедельный забег на время, не соревнование",
                        url=PARKRUN_URL, parkrun_line=True, adult_line=True),
        "kids": _empty(ids=["X:junior_parkrun"], title_en="junior parkrun — 2 km for ages 4–14", title_ru="junior parkrun — 2 км, 4–14 лет",
                       meta_en="every Sunday morning · free, register once",
                       meta_ru="каждое воскресенье утром · бесплатно, один раз зарегистрироваться на сайте",
                       kind_en="junior parkrun", kind_ru="детский забег parkrun", url=PARKRUN_URL, parkrun_line=True,
                       section_line=True),
    }


def register(pools, items: list[dict]) -> None:
    """Постоянные строки (parkrun, Volunteer Cambs) — служебные кандидаты вида standing, чтобы проверки видели id."""
    for it in items:
        for i in it.get("ids") or []:
            if i.startswith("X:") and i not in pools.candidates:
                pools.candidates[i] = {"kind": "standing", "title": it["title_en"], "url": it.get("url"), "event_ids": [],
                                       "dates": [], "sources": ["standing"], "importance": None}
