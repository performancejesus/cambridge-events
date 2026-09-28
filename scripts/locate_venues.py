"""Этап 4b: площадки без postcode — справочник → адрес в тексте страницы события/статьи (Claude Haiku) → postcodes.io.

Запуск: python scripts/locate_venues.py      (затем python scripts/update_db.py --no-load)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from pipeline import locate  # noqa: E402
from pipeline.db import connect  # noqa: E402


def main() -> None:
    from extract_articles import load_dotenv
    load_dotenv()
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["EVENTS_ANTHROPIC_KEY"])
    con = connect()
    print(json.dumps(locate.run(con, client), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
