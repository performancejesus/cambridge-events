"""Этап 7g (правки после v13 и итоги разметки 7f): правила отбора до модели.

- Не события (служебные страницы, дни открытых дверей школ и колледжей, бизнес-программы и конференции, коворкинг,
  пункты приёма, дейтинг) — в кандидаты не попадают (`nonevent_reason`).
- Частые регулярные события (ежедневные экскурсии, еженедельные прогулки, библиотечные занятия) — не в недельный
  выпуск, в базе и на сайте как «постоянное» (`frequent_regular`).
- Расплывчатые пункты («Waterstones Book Events», «Studio Sunday») — только если есть страница события с фактами
  (`vague`); иначе не берём.
- «Новое в городе»: только открытия и «скоро откроется»; не берём закрытия, заправки, медцентры, похоронные и подобные,
  безымянные «новая пиццерия» (`news_reason`).
- Детские секции и программы: взрослое — вон, продлёнки и завтраки при школах — вон, Home Ed — пометка, обязательные
  поля строки (провайдер, площадка, возраст, что за занятие) (`section_reason`, `adult`, `home_ed`).
"""

from __future__ import annotations

import re

SERVICE_RE = re.compile(r"\b(car ?park(ing)?( space)?|parking( space| permit)?|ticket protection|secure my booking|"
                        r"booking protection|refund protection|donations? page|make a donation|donate\b|gift (card|voucher)s?|"
                        r"e-?gift|become a member|membership( scheme| renewal)?\s*$)", re.I)
SERVICE_TITLES = {"space", "tickets", "ticket", "book now", "membership", "gift card", "gift voucher", "donate"}
SCHOOL_OPEN_RE = re.compile(r"\b(sixth form|6th form|year \d+ open|prospective (students|parents|pupils)|admissions? "
                            r"(event|evening)|open (day|evening|morning)s? (at|for) (the )?(school|college|academy|campus)|"
                            r"(school|college|academy|campus|university|uni) open (day|evening|morning)|"
                            r"open (evening|day)\s*[-–—:]\s*\w+ campus|undergraduate open day|postgraduate open)\b", re.I)
BUSINESS_RE = re.compile(r"\b(business (networking|owners?|buzz|breakfast|club|growth|leaders?|forum|expo|show)|"
                         r"networking( event| evening| lunch| breakfast)?|mastermind|founders'? club|b2b|for professionals|"
                         r"leadership (conference|summit|programme)|conference 20\d\d|\bsummit\b|intelligence network|"
                         r"cpd (course|event)|accelerator|investor|pitch night|entrepreneurs?|start-?up (event|night)|"
                         r"building a .{0,40}business|grow your business|trade show|industry day)\b", re.I)
COWORK_RE = re.compile(r"\bco-?work(ing)?\b", re.I)
DROPOFF_RE = re.compile(r"\b(e-?waste|recycling) (day|point|collection|drop)|\bcollection point\b|\bdrop-?off point\b|"
                        r"\be-?waste day\b", re.I)
MUSEUM_HOST_RE = re.compile(r"\b(museum|computing history|gallery)\b", re.I)
DATING_RE = re.compile(r"\b(speed ?dating|dating|singles? (night|event|party|mixer|evening)|love at first sign|"
                       r"matchmaking)\b", re.I)


def nonevent_reason(title: str, summary: str | None = None, venue: str | None = None) -> str | None:
    """Причина «не событие» или None (решения 7g: служебные страницы, школы, бизнес, коворкинг, приём, дейтинг)."""
    t = (title or "").strip()
    if DATING_RE.search(t):
        return "не событие: дейтинг (никогда)"
    if t.lower().strip(" .!") in SERVICE_TITLES or SERVICE_RE.search(t):
        return "не событие: служебная страница (парковка, страховка билета, пожертвования, подарочные карты, членство)"
    if SCHOOL_OPEN_RE.search(t):
        return "не событие: день открытых дверей школы или колледжа"
    if BUSINESS_RE.search(t):
        return "не событие: бизнес-программа или конференция для профессионалов"
    if COWORK_RE.search(t):
        return "не событие: коворкинг-бранч"
    if DROPOFF_RE.search(t) and not MUSEUM_HOST_RE.search(f"{venue or ''} {t}"):
        return "не событие: пункт приёма (E-waste и т. п.)"
    return None


SCHOOL_RE = re.compile(r"\b(?:primary|infant|junior|nursery|secondary|high|grammar|community|c of e|ce|church of england)"
                       r"\s+(?:school|academy)\b|\bacademy trust\b|\bsixth form\b|\bschool\b(?!\s+of\b)", re.I)
SCHOOL_AUDIENCE_RE = re.compile(r"\b(?:parents?|carers?|parent/carer|pupils?|students?|year \d+|reception|pta|"
                                r"governors?|families of)\b", re.I)
ORGANISER_RE = re.compile(r"Organi[sz]ed by\s*(?:\|\s*)?(?:[A-Z]\s*\|\s*)?([^|]{3,80})")


def school_event_reason(title: str, venue: str | None, page_text: str = "") -> str | None:
    """Правка 10 после v14: «Parent/Carer coaching workshop» в Milton Road Primary School — организатор сама школа
    (Eventbrite: «Organized by Milton Road Primary School»), занятие для родителей её учеников. Школьное мероприятие —
    по правилу дней открытых дверей: не в выпуск. Признаки: площадка — школа, и организатор — школа (по странице) или в
    названии родители / ученики / классы."""
    if not SCHOOL_RE.search(venue or ""):
        return None
    m = ORGANISER_RE.search(page_text or "")
    org = (m.group(1).strip() if m else "")
    if (org and SCHOOL_RE.search(org)) or SCHOOL_AUDIENCE_RE.search(title or ""):
        return "не событие: мероприятие школы для своих (родители и ученики этой школы)"
    return None


# --- частые регулярные события -----------------------------------------------------------------------------------

REGULAR_RE = re.compile(r"\b(daily|every day|each day|every (monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
                        r"weekly|every week|guided (walking )?tours?|walking tours?|city tours?|punting tours?|"
                        r"rhymetime|storytime|story time|baby bounce|lego club|knit and natter|chatterbooks|"
                        r"toddler (time|group)|stay and play|coffee morning|drop-in session)\b", re.I)
PERFORMANCE_TYPES = {"concert", "comedy", "theatre", "festival", "museum_exhibition"}


def frequent_regular(c: dict) -> str | None:
    """Ежедневные экскурсии, еженедельные прогулки, библиотечные занятия — «постоянное», не в недельный выпуск.
    Спектакль, идущий каждый вечер, и выставка — не регулярные (тэги исполнительских жанров и выставок)."""
    if re.search(r"\bparkrun\b", c.get("title") or "", re.I):
        return "parkrun — одной строкой со ссылкой на parkrun.org.uk (взрослый — «Спорт», junior — «Секции»)"
    if set(c.get("types") or []) & PERFORMANCE_TYPES:
        return None
    text = " ".join([c.get("title") or ""] + list(c.get("categories") or []))
    n_dates = len(c.get("dates") or [])
    if "library_regular" in (c.get("types") or []) or c.get("regular_series"):
        return "частое регулярное (библиотека, еженедельное занятие) — постоянное, не в недельный выпуск"
    if REGULAR_RE.search(text) and (n_dates >= 3 or re.search(r"daily|every|weekly", text, re.I)):
        return "частое регулярное (ежедневные экскурсии, еженедельные прогулки) — постоянное, не в недельный выпуск"
    if n_dates >= 5 and re.search(r"\b(tour|walk|session|club|class|group)\b", text, re.I):
        return f"частое регулярное ({n_dates} дат в окне) — постоянное, не в недельный выпуск"
    title = c.get("title") or ""
    span = 0
    if c.get("dates"):
        try:
            from datetime import date as _d
            span = (_d.fromisoformat(str(max(x[1] or x[0] for x in c["dates"]))[:10])
                    - _d.fromisoformat(str(min(x[0] for x in c["dates"]))[:10])).days
        except (ValueError, TypeError):
            span = 0
    if re.search(r"\b(mon|tues|wednes|thurs|fri|satur|sun)day (walks?|tours?|club|group|sessions?)\b|\bweekly\b", title, re.I) \
            or (span > 14 and re.search(r"\b(walks?|tours?|club|stay and play|play ?group|bumps and babies)\b", title, re.I)):
        # «Wednesday Walks» до 30 декабря, «Bumps and Babies Play» — регулярное, не новость недели
        return "частое регулярное (еженедельная прогулка, клуб, группа) — постоянное, не в недельный выпуск"
    return None


SLUG_N_RE = re.compile(r"-(\d{1,3})/?$")


def series_regular(dates: list[str], urls: list[str] | None = None, min_dates: int = 4, days: int = 31) -> str | None:
    """Правка 7 после v14: одинаковое название на одной площадке у 4+ дат в течение месяца — регулярное, даже если у
    каждой даты своя страница (Guided House Tour в Kettle's Yard). Второй признак — номер страницы серии у
    museums.cam.ac.uk («guided-house-tour-27» — 27-я дата той же экскурсии)."""
    ds = sorted({x[:10] for x in dates if x})
    from datetime import date as _d
    dd = [_d.fromisoformat(x) for x in ds]
    for i in range(len(dd)):
        n = sum(1 for y in dd[i:] if (y - dd[i]).days < days)
        if n >= min_dates:
            return f"частое регулярное (одно название на одной площадке — {n} дат за месяц, страницы разные)"
    nums = [int(m.group(1)) for u in urls or [] for m in [SLUG_N_RE.search(u or "")] if m and "museums.cam.ac.uk" in (u or "")]
    if len(ds) >= 3 and any(n >= 10 for n in nums):
        return f"частое регулярное (серия: страница №{max(nums)} той же экскурсии, {len(ds)} дат в базе)"
    return None


# --- расплывчатые пункты ------------------------------------------------------------------------------------------

VAGUE_RE = re.compile(r"\b(book events?|studio sunday|print shop open|community (evening )?classes|discovery sessions?|"
                      r"guided tour of the|open studio( day)?|drop-?in( session)?|what'?s on|activities|"
                      r"family fun|events? programme)\b|^(space|events?|activities|workshops?|tours?)$", re.I)


def vague(c: dict) -> bool:
    """Расплывчатый заголовок: по нему не понять, что именно будет."""
    return bool(VAGUE_RE.search((c.get("title") or "").strip()))


def vague_reason(c: dict) -> str | None:
    """Расплывчатый пункт без страницы события с фактами — не берём (раскрыть нечем)."""
    if vague(c) and len((c.get("page_facts") or "").split()) < 25 and len((c.get("summary") or "").split()) < 25:
        return "расплывчатый пункт: по странице не понять, что будет — не берём"
    return None


# --- «Новое в городе» ---------------------------------------------------------------------------------------------

NEWS_EXCLUDE_RE = re.compile(r"\b(petrol|filling station|fuel|service station|garage forecourt|ev charging|"
                             r"medical (centre|center|practice)|gp (surgery|practice)|surgery\b|health centre|clinic|"
                             r"dental|dentist|pharmacy|chemist|optician|hospital|care home|funeral|crematorium|cemetery|"
                             r"undertaker|bereavement|vets?\b|veterinary|bank branch|estate agent|letting agent|solicitor|"
                             r"car wash|tyre|mot centre|storage)\b", re.I)
NAMELESS_RE = re.compile(r"^(?:a |an |the )?new (pizzeria|pizza (?:place|restaurant)|restaurant|caf[eé]|coffee shop|bar|pub|"
                         r"shop|store|bakery|takeaway|deli|bistro)\b|^(?:новая|новый|новое) \w+$|\(unnamed\)|\bunnamed\b", re.I)
CLOSURE_STAGES = {"closed", "closing", "closure"}


def news_reason(c: dict) -> str | None:
    """«Новое в городе» — только открытия и «скоро откроется» (решение 11.10)."""
    if (c.get("stage") or "") in CLOSURE_STAGES or re.search(r"\bclos(ed|ing|ure|es)\b", c.get("stage") or "", re.I):
        return "«Новое в городе»: закрытие — не берём"
    text = f"{c.get('title') or ''} {c.get('summary') or ''}"
    if NEWS_EXCLUDE_RE.search(c.get("title") or "") or NEWS_EXCLUDE_RE.search(c.get("category") or ""):
        return "«Новое в городе»: заправка, медцентр, похоронное и подобное — не берём"
    if NAMELESS_RE.search((c.get("title") or "").strip()):
        return "«Новое в городе»: безымянное («новая пиццерия») — не берём"
    del text
    return None


def norm_place(name: str | None) -> str:
    """Название места для сверки дублей: без артикля, пунктуации и регистра («The Arbury Social» = «Arbury Social»)."""
    t = re.sub(r"[’'`]", "", (name or "").lower())
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"^\s*the\s+", "", t)
    t = re.sub(r"\b(cambridge|ltd|limited|restaurant|cafe|café|bar|pub|kitchen)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# --- детские секции и программы -------------------------------------------------------------------------------------

ADULT_RE = re.compile(r"\b(adults?|grown-?ups?|senior (men|women|ladies)|seniors\b|men'?s|women'?s|ladies|masters|"
                      r"veterans?|over[- ]?(50|55|60|65)s?|50\+|55\+|60\+|16\+|18\+|ages? 16 and (over|older)|"
                      r"ages? 1[6-9]\+|aged 1[6-9]\+|ages? 1[5-9] and older|parkinson'?s|walking football|"
                      r"cadmus|commercial (dance|class)|zumba gold|fitness for adults|adult fitness)\b", re.I)
WRAPAROUND_RE = re.compile(r"\b(wrap-?around|breakfast club|after[- ]school club|before[- ]school|out of school club|"
                           r"holiday club for pupils|kids club at \w+ (primary|school))\b", re.I)
HOME_ED_RE = re.compile(r"\b(home[- ]?ed(ucat\w+)?|home[- ]?school\w*|ehe\b|elective home education)\b", re.I)
HAF_RE = re.compile(r"\b(haf|holiday activities and food|free school meals|fsm)\b", re.I)
GENERIC_SECTION_RE = re.compile(r"^(academy \d+|recreational\b.*|kids|juniors?|pee ?wees|rumble tots|tots|minis|"
                                r"beginners|improvers|squad\b.*|group [a-z0-9]+|level \d+|stage \d+|class [a-z0-9]+)\s*"
                                r"(\(.*\))?$", re.I)
AGE_RE = re.compile(r"\b(\d{1,2})\s*(?:[-–]|to)\s*(\d{1,2})\b|\b(?:ages?|aged|years?|yrs?)\s*\d|\b\d{1,2}\+|"
                    r"\bunder[- ]?\d{1,2}s?\b|\bu\d{1,2}s?\b|\breception\b|\byear \d|\btoddlers?\b|\bbabies\b|"
                    r"\bpre-?school\b|\b\d{1,2}\s*(?:yrs?|years? old|y/o)\b|\bteens?\b|\bteenagers?\b", re.I)


def adult(text: str) -> bool:
    """Взрослое занятие (adult / senior men / masters / 16+ / 18+ / over 50 / walking football…)."""
    return bool(ADULT_RE.search(text or ""))


def home_ed(text: str) -> bool:
    return bool(HOME_ED_RE.search(text or ""))


PLACEHOLDER_AGES = re.compile(r"^\s*(not specified|unknown|n/?a|tbc|all ages|all levels.*)?\s*$", re.I)


def section_reason(r: dict) -> str | None:
    """Почему детскую секцию нельзя показать: взрослое, продлёнка при школе, нет обязательных полей.
    r — строка kids_programmes (провайдер, название, возраст, площадка, категория)."""
    text = " ".join(str(r.get(k) or "") for k in ("title", "ages", "note", "category"))
    if adult(text) and not re.search(r"\b(kids|children|junior|youth|teen|family)\b", r.get("title") or "", re.I):
        return "взрослое занятие — не в детской рубрике"
    if WRAPAROUND_RE.search(text):
        return "продлёнка или завтрак при школе — только для учеников этой школы"
    missing = []
    if not (r.get("provider") or "").strip():
        missing.append("провайдер")
    if not (r.get("venue") or r.get("address") or "").strip():
        missing.append("площадка")
    if not AGE_RE.search(f"{r.get('ages') or ''} {r.get('title') or ''}"):
        missing.append("возраст")
    title = (r.get("title") or "").strip()
    if GENERIC_SECTION_RE.match(title) and not (r.get("category") or "").strip():
        missing.append("что за занятие")
    if missing:
        return "нужно дополнить: нет " + ", ".join(missing)
    return None


def dup_age(title: str) -> str:
    """«Cambridge Gymnastics (11-16 yrs) (11 to 16 yrs old)» → возраст в названии один раз."""
    groups = list(re.finditer(r"\s*\(([^)]*\d[^)]*)\)", title or ""))
    seen, out = [], title
    for g in groups:
        nums = tuple(re.findall(r"\d+", g.group(1)))
        if nums in seen:
            out = out.replace(g.group(0), "", 1)
        seen.append(nums)
    return out.strip()


def fix_price_comma(price: str | None) -> str | None:
    """«£5,50» → «£5.50» (пенсы через точку; «£1,200» — тысячи, не трогаем)."""
    return re.sub(r"£\s?(\d+),(\d{2})\b(?!\d)", r"£\1.\2", price) if price else price
