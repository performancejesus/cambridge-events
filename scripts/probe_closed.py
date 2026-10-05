"""Прогон 7e+ (05.10): проверка закрывшихся сайтов после паузы — по одному спокойному запросу к главной каждого домена.

Через общий слой (collectors/http.py): robots.txt (кэш на сутки), пауза на домен, журнал request_log. Защиту не
обходим: главная ответила не 200 или заглушкой бот-защиты — пауза домена 24 ч (слой ставит её сам на 403/429/5xx и
заглушку; на прочие коды — здесь). Открылась — домен снят с паузы (probation=0), дальше — обычные правила слоя.

Запуск: python scripts/probe_closed.py            → data/probe_closed_<дата>.json
        python scripts/probe_closed.py --report   → добавить в файл «запросов за сутки» и «событий собрано»
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.http import Deferred, Disallowed, FetchError, PoliteClient, cooldown, is_challenge, state  # noqa: E402

# домен → (источник, название, хосты-синонимы с тем же решением)
SITES = [
    ("www.junction.co.uk", "S012", "Cambridge Junction", ["junction.co.uk"]),
    ("cambridgeppf.org", "S131", "Cambridge Past, Present & Future", ["www.cambridgeppf.org"]),
    ("www.visitcambridge.org", "S001", "Visit Cambridge", ["visitcambridge.org"]),
    ("www.visitwestnorfolk.com", "S183", "Visit West Norfolk", []),
    ("cus.org", "S049", "Cambridge Union", []),
    ("www.dow.cam.ac.uk", "S163", "Heong Gallery (Downing College)", []),
    ("theatreroyal.org", "S126", "Theatre Royal Bury St Edmunds", ["www.theatreroyal.org"]),
    # курсы и секции, стоявшие на паузе (этап 7e)
    ("camre.ac.uk", "S184", "Cambridge Regional College (курсы)", []),
    ("rowanhumberstone.org.uk", "S184", "Rowan Humberstone (курсы)", []),
    ("cambridgedancecentre.co.uk", "S184", "Cambridge Dance Centre (курсы)", []),
    ("unshaken-photography.co.uk", "S184", "Unshaken Photography (курсы)", []),
    ("classbento.co.uk", "S184", "ClassBento (курсы)", []),
    ("camopenstudios.org", "S184", "Cambridge Open Studios (мастер-классы)", []),
    ("haysouthcambs.co.uk", "S184", "HAY South Cambs (walking football)", []),
    ("cambridgerugby.co.uk", "S185", "Cambridge Rugby (секции)", []),
    ("cambridgerangers.com", "S185", "Cambridge Rangers (секции)", []),
    # прочие домены, которые слой сам поставил на паузу 30.09–01.10
    ("worldpeashoot.com", "R26", "World Pea Shooting Championship", []),
    ("cambridgeliteraryfestival.com", "R34", "Cambridge Literary Festival", []),
    ("elyfolkfestival.co.uk", "R41", "Ely Folk Festival", []),
    ("thebigretreatfestival.com", "R49", "The Big Retreat", []),
    ("www.peterboroughtoday.co.uk", "S010", "Peterborough Telegraph", []),
    ("cambridgefoodies.me.uk", "S087", "Cambridge Foodies", []),
    ("www.spri.cam.ac.uk", "S144", "Scott Polar Research Institute", []),
]
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def probe(today: str) -> dict:
    http = PoliteClient(purpose="probe_closed")
    out = []
    try:
        for host, sid, name, aliases in SITES:
            url = f"https://{host}/"
            rec = {"host": host, "source": sid, "name": name, "url": url,
                   "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            before = http.requests
            try:
                r = http.fetch(url)
                ch = (not r.from_cache) and is_challenge(r.status, r.content)
                m = TITLE_RE.search(r.text[:20000])
                rec.update(status=r.status, final_url=r.url, challenge=ch, bytes=len(r.content),
                           from_cache=r.from_cache, server=r.headers.get("server"),
                           title=re.sub(r"\s+", " ", m.group(1)).strip()[:120] if m else None)
                if r.status == 200 and not ch:
                    rec["result"] = "открылся"
                else:
                    rec["result"] = "новая заглушка" if ch else "закрыт"
                    st = state()
                    row = st.execute("SELECT cooldown_until FROM hosts WHERE host=?", (host,)).fetchone()
                    if not (row and row[0] and row[0] > rec["at"]):   # слой паузу не поставил (307, 404 …) — ставим
                        cooldown(host, f"прогон 7e+: главная {r.status}", 24, st)
            except Disallowed:   # robots.txt недоступен (429, 5xx, обрыв) = запрет всего сайта по RFC 9309
                rs = state().execute("SELECT robots_status FROM hosts WHERE host=?", (host,)).fetchone()
                rec.update(result="закрыт", status=None, robots_status=rs[0] if rs else None,
                           error=f"robots.txt: {rs[0] if rs else '?'} — сайт закрыт для бота целиком")
                if rs and rs[0] != 200:
                    st = state()
                    row = st.execute("SELECT cooldown_until FROM hosts WHERE host=?", (host,)).fetchone()
                    if not (row and row[0] and row[0] > rec["at"]):
                        cooldown(host, f"прогон 7e+: robots.txt {rs[0]}", 24, st)
            except Deferred as e:
                rec.update(result="на паузе", status=None, error=str(e)[:200])
            except FetchError as e:
                rec.update(result="закрыт", status=-1, error=str(e)[:200])
            rec["requests"] = http.requests - before   # robots.txt (если кэш старше суток) + главная
            st = state()
            for a in aliases:   # синонимы домена — то же решение
                if rec["result"] == "открылся":
                    st.execute("UPDATE hosts SET probation=0, cooldown_since=NULL WHERE host=?", (a,))
                else:
                    cooldown(a, f"прогон 7e+: основной домен {host} — {rec['result']}", 24, st)
            out.append(rec)
            print(f"{host:32} {rec['result']:15} {rec.get('status')} {rec.get('title') or rec.get('error') or ''}"[:160],
                  file=sys.stderr, flush=True)
    finally:
        http.close()
    return {"checked": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "note": "прогон 7e+: по одному запросу к главной после паузы (истекла 02.10); robots.txt — из кэша слоя "
                    "или один запрос, если кэш старше суток", "sites": out}


def report(path: Path) -> dict:
    """Запросов к домену за последние сутки (журнал слоя) и событий, собранных его источником в этом прогоне."""
    data = json.loads(path.read_text())
    st = state()
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
    run = json.loads((ROOT / "data" / "raw" / "_run.json").read_text())
    for s in data["sites"]:
        hosts = [s["host"]] + next(a for h, _, _, a in SITES if h == s["host"])
        q = ",".join("?" * len(hosts))
        s["requests_24h"] = st.execute(f"SELECT count(*) FROM request_log WHERE host IN ({q}) AND ts >= ? AND "
                                       "result IN ('network','not_modified','robots')", (*hosts, since)).fetchone()[0]
        s["cache_24h"] = st.execute(f"SELECT count(*) FROM request_log WHERE host IN ({q}) AND ts >= ? AND result='cache'",
                                    (*hosts, since)).fetchone()[0]
        e = run.get(s["source"]) if s["source"].startswith("S") else None
        if e and e.get("started_at", "") >= data["checked"][:10]:
            s["collect"] = {"ok": e.get("ok"), "events": e.get("events"), "requests": e.get("requests"),
                            "error": e.get("error")}
        cd = st.execute("SELECT cooldown_until, cooldown_reason FROM hosts WHERE host=?", (s["host"],)).fetchone()
        s["cooldown_now"] = dict(cd) if cd and cd[0] and cd[0] > since else None
    data["report_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return data


if __name__ == "__main__":
    today = datetime.now(timezone.utc).date().isoformat()
    path = ROOT / "data" / f"probe_closed_{today}.json"
    if "--report" in sys.argv:
        files = sorted((ROOT / "data").glob("probe_closed_*.json"))
        path = files[-1]
        res = report(path)
    else:
        res = probe(today)
    path.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(path)
