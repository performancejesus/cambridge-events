"""Этап 6d: оценка монетизации партнёрскими ссылками (только расчёт; ни в какие программы не регистрировались).

  python scripts/monetization.py            # → data/monetization_6d.json (итоги в цифрах и оценка дохода)

Входы: data/ticket_vendors_6d.json (scripts/ticket_vendors.py), data/affiliates_6d.json (условия программ),
data/monetization_params.json (допущения — меняются без правки кода).
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import domains  # noqa: E402
from pipeline.db import connect  # noqa: E402


def programme_of(vendor: str, aff: list[dict]) -> dict | None:
    v = vendor.lower()
    if v == "не определён":
        return None
    for a in aff:
        if any(m in v for m in a.get("match", [])):
            return a
    for a in aff:
        names = [a["vendor"].lower()] + [h.split(".")[0] for h in a["hosts"]]
        if any(n and n in v for n in names):
            return a
    return None


def has_programme(a: dict | None) -> bool:
    return bool(a) and a["programme"].startswith("есть")


def main() -> None:
    tv = json.loads((ROOT / "data" / "ticket_vendors_6d.json").read_text())
    aff = json.loads((ROOT / "data" / "affiliates_6d.json").read_text())["vendors"]
    par = json.loads((ROOT / "data" / "monetization_params.json").read_text())
    events = {int(k): v for k, v in tv["events"].items()}
    window = [e for e in events if e in {int(x) for x in events} and events[e].get("vendor")]
    win_ids = [int(e) for e in tv.get("window_ids", [])] or window

    def share(ids: list[int], weights: dict[int, float] | None = None) -> dict:
        w = weights or {i: 1.0 for i in ids}
        tot = sum(w[i] for i in ids) or 1
        known = [i for i in ids if events[i]["vendor"] != "не определён"]
        prog = [i for i in ids if has_programme(programme_of(events[i]["vendor"], aff))]
        email = [i for i in prog if programme_of(events[i]["vendor"], aff)["email"].startswith("разрешено")]
        return {"n": len(ids), "vendor_known": round(sum(w[i] for i in known) / tot, 3),
                "with_programme": round(sum(w[i] for i in prog) / tot, 3),
                "with_programme_email_allowed": round(sum(w[i] for i in email) / tot, 3)}

    imp = {i: max(float(events[i].get("importance") or 0), 0.5) for i in events}
    out = {"window": {"events": share(win_ids), "weighted_by_importance": share(win_ids, imp)},
           "window_by_vendor": Counter(events[i]["vendor"] for i in win_ids).most_common(), "items": {}}
    for ver, items in tv["items"].items():
        if not items:
            continue
        ids = [it["event_ids"][0] for it in items if it["event_ids"][0] in events]
        wts = {it["event_ids"][0]: max(it["importance"] or 0, 0.5) for it in items}
        out["items"][ver] = {"all": share(ids), "weighted_by_importance": share(ids, wts),
                             "by_vendor": Counter(events[i]["vendor"] for i in ids).most_common()}
    # продавцы и источники реестра с программой
    vendors_seen = sorted({events[i]["vendor"] for i in events})
    out["vendors_seen"] = [{"vendor": v, "programme": (programme_of(v, aff) or {}).get("programme", "не исследовано")}
                           for v in vendors_seen]
    out["vendors_with_programme"] = sum(1 for a in aff if has_programme(a))
    out["vendors_researched"] = len(aff)
    con = connect()
    reg = domains.registry_hosts(con)
    prog_hosts = {h for a in aff if has_programme(a) for h in a["hosts"]}
    src_with = sorted({sid for h, sids in reg.items() for sid in sids if any(h == p or h.endswith("." + p) for p in prog_hosts)})
    out["registry_sources_with_programme"] = src_with
    # оценка дохода: клики распределяются по продавцам (с учётом важности) — пунктов последнего выпуска и событий окна
    def eff(pairs: list[tuple[int, float]]) -> float:
        wsum = sum(wt for _, wt in pairs) or 1
        total = 0.0
        for eid, wt in pairs:
            a = programme_of(events[eid]["vendor"], aff)
            if not has_programme(a):
                continue
            if par["only_email_allowed"] and not a["email"].startswith("разрешено"):
                continue
            rate = a.get("commission_for_model")
            rate = par.get("unknown_programme_commission", 0) if rate is None else rate
            total += wt / wsum * rate
        return total

    last = max(out["items"]) if out["items"] else None
    items_pairs = [(it["event_ids"][0], max(it["importance"] or 0, 0.5)) for it in tv["items"].get(last, [])
                   if it["event_ids"][0] in events]
    window_pairs = [(e, imp[e]) for e in win_ids]
    out["effective_commission_share"] = {"items": round(eff(items_pairs), 4), "window": round(eff(window_pairs), 4)}
    est = {}
    for basis, rate in out["effective_commission_share"].items():
        for name, s in par["scenarios"].items():
            clicks = par["subscribers"] * par["issues_per_month"] * s["ticket_clicks_per_subscriber_per_issue"]
            orders = clicks * s["purchase_rate_after_click"]
            est[f"{basis}_{name}"] = {"clicks_per_month": round(clicks), "orders_per_month": round(orders, 1),
                                      "gbp_per_month_per_1000": round(orders * s["avg_order_gbp"] * rate, 2)}
    out["estimate"] = {"based_on_items_of": last, "params": par, "result": est}
    (ROOT / "data" / "monetization_6d.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps({k: out[k] for k in ("window", "effective_commission_share", "estimate")}, ensure_ascii=False,
                     indent=1)[:3000])


if __name__ == "__main__":
    main()
