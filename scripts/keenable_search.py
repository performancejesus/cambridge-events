"""Этап 6b: прогон поисковых запросов Keenable (data/keenable_queries.json) с кэшем.

  python scripts/keenable_search.py            # все группы: аудит (100) + провайдеры детских программ
  python scripts/keenable_search.py kids_providers
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import keenable  # noqa: E402
from pipeline.db import connect  # noqa: E402

AUDIT_GROUPS = ["categories", "towns", "openings", "open_spaces", "churches", "family_places"]


def main() -> None:
    q = json.loads((ROOT / "data" / "keenable_queries.json").read_text())
    groups = sys.argv[1:] or AUDIT_GROUPS + ["kids_providers"]
    con = connect()
    k = keenable.Keenable(con)
    for g in groups:
        purpose = "kids_providers" if g == "kids_providers" else "gap_audit"
        n = 0
        for query in q[g]:
            n += len(k.search(query, purpose))
        print(f"{g}: {len(q[g])} запросов, {n} результатов")
    print(f"запросов к API: {k.calls}, из кэша: {k.cached}")


if __name__ == "__main__":
    main()
