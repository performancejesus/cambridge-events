"""1. Проверенные факты (блокирующая).

Утверждения о днях рождения, юбилеях («исполнилось бы», «в этом месяце / году», «N-летие»), «впервые / последний /
единственный», годах основания сверяются с таблицей verified_facts. Нет в таблице или расходится — блок.
- День рождения и возраст: нужен факт birth_date о том, кто назван в предложении (или в заголовке пункта / темы);
  возраст считается от даты рождения, «в этом месяце» — только если месяц рождения совпадает с месяцем выпуска.
- «Первый / последний / единственный», год основания, «уже в N-й раз»: факт в таблице или утверждение найдено в тексте
  источника пункта (сверка r02) — тогда сборщик заносит его в verified_facts с источником = страница пункта.
Постоянный регрессионный тест: Syd Barrett родился 6 января 1946; «в этом месяце исполнилось бы 80» в октябре — ошибка
(tests/test_regressions.py).
"""

from __future__ import annotations

import re
from datetime import date

from pipeline import verified_facts
from . import BLOCK, Finding

RULE, TITLE, LEVEL = 1, "Проверенные факты (дни рождения, юбилеи, «первый / последний / единственный»)", BLOCK

WORDNUM = {"second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
           "второй": 2, "третий": 3, "четвёртый": 4, "четвертый": 4, "пятый": 5, "шестой": 6, "седьмой": 7, "восьмой": 8,
           "девятый": 9, "десятый": 10}
AGE_RE = [re.compile(r"исполнил\w*\s+бы\s+(\d+)", re.I), re.compile(r"исполня\w+\s+(\d+)", re.I),
          re.compile(r"(\d+)[-‑ ]?лети\w*", re.I), re.compile(r"(\d+)\s+лет\s+со\s+дня\s+рождения", re.I),
          re.compile(r"would\s+have\s+(?:turned|been)\s+(\d+)", re.I), re.compile(r"\bturns?\s+(\d+)\b", re.I),
          re.compile(r"\b(\d+)(?:st|nd|rd|th)[\s-]+(?:birthday|anniversary)", re.I)]
BIRTH_RE = re.compile(r"родил\w*|дн[яё]\w* рождени\w*|день рождени\w*|исполнил\w*\s+бы|\bborn\b|\bbirthday\b|"
                      r"would have (?:turned|been)", re.I)
MONTH_RE = re.compile(r"в этом месяце|этим месяцем|в этом октябре|this month|this october", re.I)
YEAR_RE = re.compile(r"в этом году|this year", re.I)
SUPER_RE = re.compile(r"\bвпервые\b|\bперв(?:ый|ая|ое|ые|ого|ой|ую|ым|ом)\b|\bпоследн\w+|\bединственн\w+|\bстарейш\w+|"
                      r"\bfirst(?:[- ]ever)?\b|\bthe only\b|\bonly (?:one|time|chance)\b|\boldest\b|\bfinal (?:concert|gig|"
                      r"performance|show)\b|\blast (?:concert|gig|performance|show|live)\b", re.I)
SUPER_SKIP = re.compile(r"последн\w+ (?:дв|тр|нескольк|год|месяц|недел)|\blast (?:year|month|week|few)\b|"
                        r"последн\w+ (?:билет|мест)|\blast (?:remaining |few )?(?:tickets|seats|places)\b", re.I)
# прогон 7e+: «остались последние билеты» — пометка «мало билетов» со страницы продавца, а не «последний концерт»
FOUNDED_RE = re.compile(r"основан\w*\s+в\s+(\d{4})|с\s+(\d{4})\s+года|founded\s+in\s+(\d{4})|established\s+in\s+(\d{4})|"
                        r"\bsince\s+(\d{4})", re.I)
EDITION_RE = re.compile(r"(?:уже\s+)?в\s+(\d+|\w+)[-‑]?(?:й|ый|ой|ий)?\s+раз\b|\b(\d+|second|third|fourth|fifth|\w+th)\s+"
                        r"(?:edition|year running|annual)\b", re.I)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", text or "") if s.strip()]


def classify(sent: str) -> set[str]:
    kinds = set()
    if any(rx.search(sent) for rx in AGE_RE) or BIRTH_RE.search(sent):
        kinds.add("age")
    if MONTH_RE.search(sent) and ("age" in kinds or re.search(r"юбиле|годовщин|anniversar", sent, re.I)):
        kinds.add("month")
    if SUPER_RE.search(sent) and not (SUPER_SKIP.search(sent) and not re.search(r"впервые|единствен|first|only", sent, re.I)):
        kinds.add("super")
    if FOUNDED_RE.search(sent):
        kinds.add("founded")
    m = EDITION_RE.search(sent)
    if m and (m.group(1) or m.group(2) or "").lower() in WORDNUM | {str(i): i for i in range(2, 200)}:
        kinds.add("edition")
    return kinds


def risky_sentences(ctx) -> list[dict]:
    """Предложения выпуска с проверяемыми утверждениями: {key, where, lang, sentence, kinds, context, ids}."""
    out = []
    theme_ids = [i for rub, it in ctx.model_items() if rub == "theme" for i in it["ids"]]
    blocks = [("вступление", lang, ctx.result.get(f"intro_{lang}") or "", theme_ids, "") for lang in ("ru", "en")]
    blocks += [("вступление темы", lang, ctx.result.get(f"theme_intro_{lang}") or "", theme_ids,
                ctx.result.get(f"theme_title_{lang}") or "") for lang in ("ru", "en")]
    for rub, it in ctx.model_items():
        for lang in ("ru", "en"):
            blocks.append((it.get(f"title_{lang}") or "", lang, f"{it.get(f'title_{lang}') or ''}. {it.get(f'blurb_{lang}') or ''}",
                           it["ids"], (ctx.result.get(f"theme_title_{lang}") or "") if rub == "theme" else ""))
    for where, lang, text, ids, ctx_title in blocks:
        for s in split_sentences(text):
            k = classify(s)
            if k:
                out.append({"key": f"{lang}|{s}", "where": where, "lang": lang, "sentence": s, "kinds": sorted(k),
                            "context": f"{where} {ctx_title}", "ids": ids})
    return out


def ages(sent: str) -> list[int]:
    return [int(m.group(1)) for rx in AGE_RE for m in rx.finditer(sent)]


def check(ctx) -> Finding:
    f = Finding()
    facts = verified_facts.all_facts(ctx.con)
    births = [x for x in facts if x["kind"] == "birth_date"]
    verdicts = (ctx.claims or {}).get("sentences", {})
    issue: date = ctx.w.issue
    seen = set()
    for r in risky_sentences(ctx):
        s, kinds = r["sentence"], set(r["kinds"])
        if (s, tuple(kinds)) in seen:
            continue
        seen.add((s, tuple(kinds)))
        subj = [b for b in births if verified_facts.mentions(b, s)] or \
            [b for b in births if verified_facts.mentions(b, r["context"])]
        v = verdicts.get(r["key"], {})
        supported = v.get("verdict") in ("supported", "not_a_claim")
        if kinds & {"age", "month"}:
            if not subj:
                if not supported or "month" in kinds:
                    f.violations.append(f"«{s}» ({r['where']}): возраст / день рождения — нет в verified_facts")
            else:
                b = date.fromisoformat(subj[0]["value"])
                turning = issue.year - b.year
                bad = [n for n in ages(s) if n not in (turning, turning - (0 if (issue.month, issue.day) >= (b.month, b.day) else 1))]
                if bad:
                    f.violations.append(f"«{s}» ({r['where']}): {subj[0]['subject']} родился {b:%d.%m.%Y} — в "
                                        f"{issue.year} году ему {turning}, а не {bad[0]}")
                if "month" in kinds and b.month != issue.month:
                    f.violations.append(f"«{s}» ({r['where']}): «в этом месяце» — ошибка: {subj[0]['subject']} родился "
                                        f"{b:%d.%m.%Y} (источник: {subj[0]['source']})")
        for kind in sorted(kinds & {"super", "founded", "edition"}):
            want = {"super": ("first", "last", "only", "other"), "founded": ("founded",), "edition": ("other", "first")}[kind]
            ok = any(x["kind"] in want and verified_facts.mentions(x, s) for x in facts)
            if ok or supported:
                continue
            why = v.get("verdict") or "сверка с источником не выполнялась"
            f.violations.append(f"«{s}» ({r['where']}): утверждение «{kind}» не подтверждено (verified_facts — нет; "
                                f"источник — {why})")
            break
    f.info.append(f"предложений с проверяемыми утверждениями: {len(seen)}")
    return f
