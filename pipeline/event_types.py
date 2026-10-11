"""Этап 7g (итоги разметки 7f): тэги типа события, категория для разнообразия и редакторский приоритет.

Тэги (для разнообразия рубрик и для подписки по темам на этапе 8): traditions_fairs_markets, new_venue, family_hands_on,
museum_exhibition, museum_talk, concert, comedy, theatre, library_regular, academic_seminar, local_sport, racing,
festival, volunteering, quirky_local, adult_class (+ film, talk — для раскладки по рубрикам).

Категория — одна на событие («Главное на выходные»: по 1–2 из каждой категории): kids, museum, concert, comedy,
theatre, sport, traditions, talk, film, volunteering, other.

Редакторский приоритет (уточнение 11.10): оценки редактора — не цель формулы; важность (pipeline/importance.py) не
меняется, а к ней в отборе добавляется бонус: детские и семейные +1.5, музеи, выставки и усадьбы +1.5, местное и
уникальное (традиции, сезонное, новые заведения) +0.5. rank = importance + бонус.
"""

from __future__ import annotations

import re

TAGS = ["traditions_fairs_markets", "new_venue", "family_hands_on", "museum_exhibition", "museum_talk", "concert",
        "comedy", "theatre", "library_regular", "academic_seminar", "local_sport", "racing", "festival",
        "volunteering", "quirky_local", "adult_class"]

FAIR_RE = re.compile(r"\b(fair|fayre|market|car boot|craft show|food festival|farmers'? market|makers'? market|"
                     r"christmas market|bazaar|fete|fête|harvest (weekend|festival)|apple day|wassail)\b", re.I)
SEASONAL_RE = re.compile(r"\b(halloween|bonfire|fireworks?|guy fawkes|christmas|santa|advent|harvest|pumpkin|"
                         r"easter|diwali|lantern|winter wonderland|spooky|trick or treat)\b", re.I)
MUSEUM_VENUE_RE = re.compile(r"\b(museum|fitzwilliam|kettle'?s yard|gallery|polar museum|sedgwick|whipple|"
                             r"heong|ucm|museum of cambridge|computing history|stained glass|abbey|hall|estate|wimpole|"
                             r"anglesey|audley end|duxford|ickworth|national trust|english heritage|botanic garden)\b", re.I)
EXHIBITION_RE = re.compile(r"\b(exhibition|exhibit|display|installation|retrospective|showcase of works|on show|"
                           r"collection|open studios?)\b", re.I)
TALK_RE = re.compile(r"\b(talk|lecture|in conversation|q ?& ?a|book launch|panel|discussion|reading|meet the "
                     r"(author|director)|literary|poetry|salon|author event|book event)\b", re.I)
SEMINAR_RE = re.compile(r"\b(seminar|colloquium|symposium|workshop series|research (talk|seminar)|department(al)? "
                        r"seminar|phd|postdoc|journal club|work in progress)\b", re.I)
CONCERT_RE = re.compile(r"\b(concert|gig|live music|band|orchestra|choir|jazz|folk|rock|recital|quartet|symphony|"
                        r"tribute|singer|songwriter|acoustic|dj|organ|ensemble|philharmonic|sinfonia|opera)\b", re.I)
COMEDY_RE = re.compile(r"\b(comedy|comedian|stand-?up|improv|sketch show|footlights|smoker)\b", re.I)
THEATRE_RE = re.compile(r"\b(theatre|play|musical|ballet|dance show|panto(mime)?|shakespeare|drama|production of|"
                        r"opera|circus|cabaret)\b", re.I)
LIBRARY_RE = re.compile(r"\b(rhymetime|storytime|story time|baby bounce|lego club|knit and natter|chatterbooks|"
                        r"code club|homework club|reading group|library)\b", re.I)
RACING_RE = re.compile(r"\b(raceday|race ?day|racing|newmarket|huntingdon racecourse|rowley mile|july course|"
                       r"handicap|stakes|point-?to-?point)\b", re.I)
SPORT_RE = re.compile(r"\b(fc|united|city fc|rufc|rugby|hockey|football|match|v\.?s?\.? |cricket|netball|basketball|"
                      r"ice hockey|phantoms|parkrun|athletics|boxing|darts|rowing|regatta|bumps)\b", re.I)
VOLUNTEER_RE = re.compile(r"\b(volunteer\w*|work party|working party|conservation (task|day|work)|practical "
                          r"conservation|litter pick\w*|clean-?up|river clean|tree planting|hedge laying|green gym|"
                          r"scrub clearance|habitat management|balsam bash)\b", re.I)
ADULT_CLASS_RE = re.compile(r"\b(workshop|masterclass|class|course|lesson|taster|beginners|learn to|"
                            r"how to|tuition|session for adults)\b", re.I)
FESTIVAL_RE = re.compile(r"\bfestival\b|\bfest\b|\bpride\b", re.I)
FILM_RE = re.compile(r"\b(film|screening|cinema|documentary|movie|nt live|met opera|royal opera live)\b", re.I)
CATEGORY_OF = [("family_hands_on", "kids"), ("museum_exhibition", "museum"), ("museum_talk", "museum"),
               ("comedy", "comedy"), ("theatre", "theatre"), ("concert", "concert"), ("racing", "sport"),
               ("local_sport", "sport"), ("quirky_local", "traditions"), ("traditions_fairs_markets", "traditions"),
               ("festival", "traditions"), ("volunteering", "volunteering"), ("academic_seminar", "talk"),
               ("adult_class", "class"), ("new_venue", "other")]
BONUS = {"kids": 1.5, "museum": 1.5, "local": 0.5}


def tags(c: dict) -> list[str]:
    """Тэги типа по названию, категориям источника, площадке и признакам кандидата."""
    title = c.get("title") or ""
    # название, категории источника и начало описания (у комика в названии бывает только имя: «Nish Kumar: …»)
    text = " ".join([title] + list(c.get("categories") or []) + [(c.get("summary") or "")[:300],
                                                                 (c.get("importance_reason") or "")[:200]])
    text = re.sub(r"\b(Comedy|Music|Theater|Theatre|Dance|Exhibition|Childrens|Sports|Education|Food|Literary|Visual"
                  r"Arts|Screening|Festival)Event\b", lambda m: {"Music": "concert", "Childrens": "children",
                                                                  "Theater": "theatre", "Sports": "sport match",
                                                                  "Education": "workshop", "Literary": "talk",
                                                                  "Screening": "film screening"}.get(m.group(1), m.group(1))
                  + " event", text)
    venue = " ".join(x for x in (c.get("venue") or "", c.get("address") or "") if x)
    out = []
    k = c.get("kind")
    if k == "venue_news":
        return ["new_venue"]
    if c.get("quirky"):
        out.append("quirky_local")
    if FAIR_RE.search(title):
        out.append("traditions_fairs_markets")
    if c.get("festival") or FESTIVAL_RE.search(title):
        out.append("festival")
    if VOLUNTEER_RE.search(text):
        out.append("volunteering")
    if c.get("kids_tag") and c.get("for_kids", True):
        out.append("family_hands_on")
    if LIBRARY_RE.search(text) or set(c.get("sources") or []) == {"S055"}:
        out.append("library_regular")
    if MUSEUM_VENUE_RE.search(venue) or MUSEUM_VENUE_RE.search(title):
        if EXHIBITION_RE.search(text) or c.get("long_running"):
            out.append("museum_exhibition")
        elif TALK_RE.search(text):
            out.append("museum_talk")
    elif c.get("long_running") and EXHIBITION_RE.search(text):
        out.append("museum_exhibition")
    if SEMINAR_RE.search(text) and not c.get("public_talk"):
        out.append("academic_seminar")
    if RACING_RE.search(text) or "S021" in (c.get("sources") or []) or "S022" in (c.get("sources") or []):
        out.append("racing")
    elif SPORT_RE.search(title) or c.get("participant") or set(c.get("sources") or []) & {"S018", "S123"}:
        out.append("local_sport")
    if COMEDY_RE.search(text):
        out.append("comedy")
    elif THEATRE_RE.search(text) or c.get("theatre"):
        out.append("theatre")
    if CONCERT_RE.search(text) and "comedy" not in out and not c.get("film"):
        out.append("concert")
    if ADULT_CLASS_RE.search(title) and not c.get("for_kids") and not c.get("kids_tag"):
        out.append("adult_class")
    return list(dict.fromkeys(out))


def category(c: dict, tg: list[str] | None = None) -> str:
    tg = tg if tg is not None else tags(c)
    if c.get("film") or c.get("kind") == "film_release":
        return "film"
    for t, cat in CATEGORY_OF:
        if t in tg:
            return cat
    if c.get("talk") or TALK_RE.search(c.get("title") or ""):
        return "talk"
    return "other"


def bonus(c: dict, tg: list[str] | None = None) -> float:
    """Редакторский приоритет (уточнение 11.10): детские/семейные и музеи — +1.5; местное и уникальное — +0.5."""
    tg = tg if tg is not None else tags(c)
    b = 0.0
    if "family_hands_on" in tg:
        b += BONUS["kids"]
    if {"museum_exhibition", "museum_talk"} & set(tg):
        b += BONUS["museum"]
    if {"traditions_fairs_markets", "quirky_local", "new_venue"} & set(tg) or SEASONAL_RE.search(c.get("title") or ""):
        b += BONUS["local"]
    return b


def annotate(c: dict) -> dict:
    """Дописать в кандидата: types, category, rank (= importance + бонус)."""
    tg = tags(c)
    c["types"] = tg
    c["category"] = category(c, tg)
    c["rank"] = round((c.get("importance") or 0) + bonus(c, tg), 2)
    return c
