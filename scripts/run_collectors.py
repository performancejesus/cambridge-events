"""Этап 2: запуск коллекторов. Сырые события → data/raw/<ID>_<модуль>.json, сводка → data/raw/_run.json.

Запуск: python scripts/run_collectors.py            # все
        python scripts/run_collectors.py S005 S047  # выбранные
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.http import PoliteClient  # noqa: E402
from collectors.sources import ALL  # noqa: E402

RAW = ROOT / "data" / "raw"


def main(ids: list[str]) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    summary_path = RAW / "_run.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() and ids else {}
    http = PoliteClient()
    try:
        for c in ALL:
            if ids and c.source_id not in ids:
                continue
            module = type(c).__module__.rsplit(".", 1)[-1]
            print(f"{c.source_id} {c.name} …", file=sys.stderr, flush=True)
            t0, before = time.monotonic(), http.requests
            entry = {"name": c.name, "module": module,
                     "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            try:
                events = c.collect(http)
                (RAW / f"{c.source_id}_{module}.json").write_text(
                    json.dumps([e.to_dict() for e in events], ensure_ascii=False, indent=1))
                entry.update(ok=True, events=sum(e.kind == "event" for e in events),
                             articles=sum(e.kind == "article" for e in events))
                if getattr(c, "stats", None):
                    entry["stats"] = c.stats
            except Exception as e:  # noqa: BLE001 — один упавший коллектор не останавливает прогон
                entry.update(ok=False, error=f"{type(e).__name__}: {e}"[:500],
                             trace=traceback.format_exc(limit=3)[-1500:])
            entry.update(requests=http.requests - before, seconds=round(time.monotonic() - t0, 1))
            summary[c.source_id] = entry
            print(f"   → {'ok' if entry['ok'] else 'FAIL'} {entry.get('events', '')} {entry.get('articles', '')} "
                  f"{entry.get('error', '')}", file=sys.stderr, flush=True)
            summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    finally:
        http.close()


if __name__ == "__main__":
    main(sys.argv[1:])
