"""Этап 4b: оценка важности будущих событий (importance_score 1–10, importance_reason).

Запуск: python scripts/score_importance.py            # модель (Claude Sonnet, кэш) + Wikipedia + сигналы базы
        python scripts/score_importance.py --no-model # только сигналы базы и кэш
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from pipeline import importance  # noqa: E402
from pipeline.db import connect  # noqa: E402


def main() -> None:
    client = None
    if "--no-model" not in sys.argv:
        from extract_articles import load_dotenv
        load_dotenv()
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["EVENTS_ANTHROPIC_KEY"])
    con = connect()
    print(json.dumps(importance.run(con, client), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
