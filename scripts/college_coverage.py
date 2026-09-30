"""Этап 7b: таблица покрытия колледжей — решение по каждому из 31 колледжа, события в базе до и после этапа.

  python scripts/college_coverage.py     # после аудита (data/college_audit_7b.json) и свежего сбора
    → data/college_coverage_7b.json, строки «Не разобрано» для закрытых сайтов (unparsed_sources)

«До» — события в базе за последние/следующие 60 дней на дату аудита (до новых коллекторов), «после» — сейчас.
Колледж «покрыт», если его публичные события приходят хотя бы из одного подключённого источника (свой коллектор или
общий: cmp.cam.ac.uk, talks.cam, Camdram, NGS, хор) или публичной афиши у колледжа нет (только выпускники/студенты).
"""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from college_audit import COLLEGES, db_counts  # noqa: E402
from pipeline import unparsed  # noqa: E402
from pipeline.db import connect  # noqa: E402

# колледж → (страница публичных событий, что там, фид, решение, источники, закрыт (тип проблемы, подробности) | None)
D = {
    "Christ's": ("christs.cam.ac.uk/events", "только встречи выпускников; сады и выставка библиотеки — часы посещения",
                 "—", "публичной афиши нет — не подключаем", [], None),
    "Churchill": ("chu.cam.ac.uk/events/list/ + archives.chu.cam.ac.uk/events/",
                  "лекции Archives Centre (Roskill Lecture), события колледжа, выпускники", "iCal, JSON-LD (The Events Calendar)",
                  "подключён S169 (публичные, без выпускников)", ["S169", "S150"], None),
    "Clare": ("clare.cam.ac.uk/alumni/events", "выпускники; концерты хора — на clarecollegechoir.com",
              "—", "концерты — через cmp.cam.ac.uk (S150); сайт хора — обрыв соединения", ["S150"],
              ("connection", "clarecollegechoir.com: обрыв соединения (tunnel closed) — robots.txt не прочитан",
               "https://clarecollegechoir.com/events/category/concerts", "Choir of Clare College — концерты")),
    "Clare Hall": ("clarehall.cam.ac.uk/events/", "лекции (Tanner, Ashby), концерты, выставки", "RSS",
                   "подключён S170", ["S170", "S150"], None),
    "Corpus Christi": ("corpus.cam.ac.uk/events", "заглушка Sucuri", "—",
                       "закрыт бот-защитой; Corpus Playroom — через Camdram (S168), концерты — S150", ["S168", "S150"],
                       ("bot_challenge", "Sucuri: «Please wait while your request is being verified»",
                        "https://www.corpus.cam.ac.uk/events", "Corpus Christi College — события, Parker Library")),
    "Darwin": ("darwin.cam.ac.uk/lectures", "Darwin College Lecture Series (Lent)", "—",
               "покрыт talks.cam (список 5358, S047)", ["S047"], None),
    "Downing": ("dow.cam.ac.uk/about/events", "заглушка Sucuri (с перерывами)", "—",
                "Heong Gallery — S163; Howard Theatre — Camdram (S168); сады — NGS (S067)", ["S163", "S168", "S067"],
                ("bot_challenge", "Sucuri: страницы событий и садов — заглушка; Heong Gallery открывается",
                 "https://www.dow.cam.ac.uk/about/events", "Downing College — события")),
    "Emmanuel": ("emma.cam.ac.uk/members/events", "только выпускники (Emmanuel Society)", "—",
                 "не подключаем; концерты ECMS — S150", ["S150"], None),
    "Fitzwilliam": ("fitz.cam.ac.uk/listing/whats-on", "без дат (выпускники)", "—", "публичной афиши нет", [], None),
    "Girton": ("girton.cam.ac.uk/upcoming-events", "концерты, лекции; выпускники", "—", "подключён S174",
               ["S174", "S150"], None),
    "Gonville & Caius": ("cai.cam.ac.uk", "заглушка Sucuri; хор — gonvilleandcaiuschoir.com (обрыв)", "—",
                         "закрыт бот-защитой", [],
                         ("bot_challenge", "Sucuri на cai.cam.ac.uk; gonvilleandcaiuschoir.com — обрыв соединения",
                          "https://gonvilleandcaiuschoir.com/concerts-broadcasts", "Gonville & Caius — события, концерты хора")),
    "Homerton": ("homerton.cam.ac.uk/current-members/events", "заглушка Sucuri", "—", "закрыт бот-защитой", [],
                 ("bot_challenge", "Sucuri: «Please wait while your request is being verified»",
                  "https://www.homerton.cam.ac.uk/homerton-life/kate-pretty-lectures", "Homerton — Kate Pretty Lectures")),
    "Hughes Hall": ("hughes.cam.ac.uk/about/events/", "в основном для студентов; публичные — Lightning Talks, ярмарки",
                    "—", "подключён S175 (только публичные)", ["S175", "S150"], None),
    "Jesus": ("jesus.cam.ac.uk/college/events", "редирект-петля 307 (бот-защита)", "—",
              "закрыт; spoken word и концерты — S150", ["S150"],
              ("bot_challenge", "307 на все страницы событий (защита Pantheon/Sucuri)", "https://www.jesus.cam.ac.uk/college/events",
               "Jesus College — события, John Hughes Arts Festival")),
    "King's": ("kingscollegechoir.com/concert/", "концерты хора, органная серия; лекции — talks.cam", "—",
               "покрыт S149 (хор) и S047", ["S149", "S047", "S148"], None),
    "Lucy Cavendish": ("lucy.cam.ac.uk/events", "лекции, панели, выставки", "—", "подключён S171", ["S171"], None),
    "Magdalene": ("magd.cam.ac.uk/about/events", "только выпускники и первокурсники", "—",
                  "публичной афиши нет; Pepys Library — часы посещения", [], None),
    "Murray Edwards": ("murrayedwards.cam.ac.uk/news-events", "заглушка Sucuri", "—",
                       "The Women's Art Collection — S164", ["S164"],
                       ("bot_challenge", "Sucuri на страницах событий; Women's Art Collection открывается",
                        "https://www.murrayedwards.cam.ac.uk/news-events/upcoming-events", "Murray Edwards — события")),
    "Newnham": ("newn.cam.ac.uk/events-alumnae", "только выпускницы; сады — по записи", "—",
                "публичной афиши нет; концерты — S150", ["S150"], None),
    "Pembroke": ("pem.cam.ac.uk/college/events/all", "307 (бот-защита)", "—",
                 "закрыт; Bliss Song Series — S150, S091; New Cellars — Camdram", ["S150", "S168"],
                 ("bot_challenge", "307 на все страницы (защита)", "https://pem.cam.ac.uk/college/events/all",
                  "Pembroke — события, Open Doors Festival")),
    "Peterhouse": ("pet.cam.ac.uk/music-peterhouse", "музыка без дат; часть сайта закрыта robots.txt", "—",
                   "публичной афиши нет", [], None),
    "Queens'": ("queens.cam.ac.uk", "202 — проверка бот-защиты", "—",
                "закрыт; Fitzpatrick Hall и Black Box — Camdram (S168), концерты — S150", ["S168", "S150"],
                ("bot_challenge", "202 с заглушкой на все страницы", "https://queens.cam.ac.uk/about-us/news-events",
                 "Queens' College — события")),
    "Robinson": ("robinson.cam.ac.uk/events", "концерты; много внутренних занятий для студентов", "—",
                 "подключён S172 (только публичные); сады — NGS (S067); Brickhouse — Camdram", ["S172", "S067", "S168"], None),
    "St Catharine's": ("caths.cam.ac.uk/alumni-friends/events", "307 (бот-защита)", "—", "закрыт", [],
                       ("bot_challenge", "307 на все страницы", "https://caths.cam.ac.uk/about-us/college-calendar",
                        "St Catharine's — события")),
    "St Edmund's": ("st-edmunds.cam.ac.uk/the-vhi/vhi-events/", "лекции Von Hügel Institute", "—", "подключён S173",
                    ["S173"], None),
    "St John's": ("joh.cam.ac.uk/festival + sjcchoir.co.uk/events", "лекции, концерты, хор", "—",
                  "покрыт S144 (этап 6c)", ["S144"], None),
    "Selwyn": ("sel.cam.ac.uk/events", "органные и вокальные вечера", "—", "покрыт S150 (12 событий)", ["S150"], None),
    "Sidney Sussex": ("sid.cam.ac.uk/about-sidney/events", "заглушка Sucuri", "—", "закрыт бот-защитой", [],
                      ("bot_challenge", "Sucuri: «Please wait while your request is being verified»",
                       "https://www.sid.cam.ac.uk/about-sidney/sidney-greats-lecture-series", "Sidney Sussex — Sidney Greats lectures")),
    "Trinity": ("trin.cam.ac.uk/events/ + /about/public-lectures/", "публичные лекции (Birkbeck), выпускники",
                "iCal, JSON-LD", "подключён S166 (только публичные); хор — 403", ["S166", "S150"],
                ("http_403", "trinitycollegechoir.com: 403 на все страницы", "https://trinitycollegechoir.com/concerts",
                 "Choir of Trinity College — концерты")),
    "Trinity Hall": ("trinhall.cam.ac.uk/events/", "лекции и концерты — для членов колледжа и выпускников", "RSS",
                     "не подключаем; Graham Storey Room — Camdram", ["S168"], None),
    "Wolfson": ("wolfson.cam.ac.uk/whats-on", "307 (бот-защита)", "—", "закрыт; концерты — S150, лекции CPPF — S131",
                ["S150", "S131"],
                ("bot_challenge", "307 и заглушка на страницах событий", "https://wolfson.cam.ac.uk/whats-on",
                 "Wolfson College — события и лекции")),
}


def main() -> None:
    audit = {c["college"]: c for c in json.loads((ROOT / "data" / "college_audit_7b.json").read_text())["colleges"]}
    con = connect()
    rows = []
    for name, home, pattern, _ in COLLEGES:
        page, what, feed, decision, srcs, blocked = D[name]
        before, after = audit[name]["db"], db_counts(con, pattern, date.today())
        if blocked:
            kind, detail, url, what_lost = blocked
            unparsed.record(con, f"C:{name}", f"{name} — сайт колледжа", url, kind, detail, what_lost,
                            "не обходим; перепроверить позже; публичные события частично приходят из общих источников")
        rows.append({"college": name, "page": page, "what": what, "feed": feed, "robots": audit[name]["robots"],
                     "before": {"past_60": before["past_60"], "next_60": before["next_60"], "sources": before["sources"]},
                     "after": {"past_60": after["past_60"], "next_60": after["next_60"], "sources": after["sources"],
                               "examples": after["examples"]},
                     "decision": decision, "sources": srcs, "blocked": bool(blocked),
                     "covered_before": before["next_60"] > 0, "covered_after": after["next_60"] > 0})
    con.commit()
    out = {"checked": date.today().isoformat(), "colleges": rows,
           "summary": {"covered_before": sum(r["covered_before"] for r in rows),
                       "covered_after": sum(r["covered_after"] for r in rows),
                       "own_collector": sum(1 for r in rows if "подключён" in r["decision"]),
                       "blocked": sum(r["blocked"] for r in rows),
                       "no_public_programme": sum(1 for r in rows if "афиши нет" in r["decision"]
                                                  or "не подключаем" in r["decision"])}}
    (ROOT / "data" / "college_coverage_7b.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
