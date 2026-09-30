"""Этап 7c: обязательные проверки на уже собранном выпуске (tests/issue_rules) без пересборки.

  python scripts/check_issue.py --issue 2026-10-08 --version v9            # проверки v9 (как если бы они были тогда)
  EVENTS_DB=/путь/к/снимку.db python scripts/check_issue.py ...             # на снимке базы, на котором собран выпуск
  python scripts/check_issue.py ... --no-links --no-api                     # без сети и без сверки с источниками

Результат — issues/<выпуск>_checks.json (send_allowed, блокирующие причины, все проверки) и таблица в stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import issue  # noqa: E402
from pipeline.db import connect  # noqa: E402
from tests import issue_rules  # noqa: E402
from tests.issue_rules.common import Ctx  # noqa: E402
from tests.issue_rules.runner import full_run  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--no-links", action="store_true")
    ap.add_argument("--no-api", action="store_true")
    ap.add_argument("--out", help="куда записать результат (по умолчанию issues/<выпуск>_checks.json)")
    args = ap.parse_args()
    from scripts import build_issue as B
    sent = date.fromisoformat(args.issue)
    w = issue.Window(sent, sent, sent + timedelta(days=issue.WINDOW_DAYS))
    stem = f"issue_{args.issue}_{args.version}"
    out_dir = ROOT / "issues"
    con = connect()
    saved = json.loads((out_dir / f"{stem}_model.json").read_text())
    post = saved.get("result_post") or {"result": saved["result"], "removed": {}, "notes": []}
    result, removed = post["result"], post.get("removed", {})
    pools = issue.build_pools(con, w)
    for sec in result["sections"]:
        sec["items"] = [it for it in sec["items"] if not it.get("auto")]
    B.also_playing(result, pools, w)
    html = {f"reader_{lang}": (out_dir / f"{stem}_reader_{lang}.html").read_text()
            for lang in ("ru", "en") if (out_dir / f"{stem}_reader_{lang}.html").exists()}
    lists = B.editor_lists(result, pools, w, removed, con)
    ctx = Ctx(w=w, version=args.version, result=result, pools=pools, con=con, out_dir=out_dir, stem=stem, html=html,
              lists=lists, fix_log={int(k): v for k, v in (post.get("fix_log") or {}).items()},
              missing_reasons=lists.get("_missing_reasons", []),
              options={"links": not args.no_links, "api": not args.no_api})
    client = None
    if not args.no_api and os.environ.get("EVENTS_ANTHROPIC_KEY"):
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["EVENTS_ANTHROPIC_KEY"])
    http = None
    if not args.no_links:
        from collectors.http import PoliteClient
        http = PoliteClient()
    outcomes, cost = full_run(ctx, client, http)
    path = Path(args.out) if args.out else out_dir / f"{stem}_checks.json"
    data = issue_rules.save(outcomes, path, args.issue, args.version)
    for row in issue_rules.table_rows(outcomes):
        print(row)
    print(json.dumps({"send_allowed": data["send_allowed"], "blocking": len(data["blocking"]), "claims_cost_usd": round(cost, 4),
                      "out": str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
