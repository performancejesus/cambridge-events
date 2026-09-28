"""Этап 6-v4: отчёт → docs/stage6v4_report.md: решения после этапа 6, детские программы на каникулы, выпуск v4
(пункты по рубрикам), замер по ИИ-запретам, расход."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.db import connect  # noqa: E402

STAGE_START = "2026-09-28T19:19:29+00:00"   # коммит брифа этапа 6-v4
HOL = {"october_half_term": "октябрьские каникулы (26–30 октября)", "christmas": "рождественские (21 декабря – 1 января)",
       "both": "обе (университетская программа)"}


def main() -> None:
    con = connect()
    kd = json.loads((ROOT / "data" / "kids_programmes.json").read_text())
    progs = kd["programmes"]
    L = [f"# Этап 6-v4 — выпуск v4 для читателей ({date.today().isoformat()})", ""]
    notes = ROOT / "docs" / "stage6v4_notes.md"
    if notes.exists():
        L += [notes.read_text().strip(), ""]

    L += ["## Детские программы на каникулы (`kids_programmes`)", "",
          "Даты каникул — сайт Cambridgeshire County Council: октябрьские 26–30 октября 2026, рождественские "
          "21 декабря 2026 – 1 января 2027. Программы найдены веб-поиском и проверены на сайте провайдера (robots.txt "
          "уважается); данные — `data/kids_programmes.json`, таблица `kids_programmes` (схема этапа 6c).", ""]
    cnt = Counter((p["holiday"], p.get("verified", False)) for p in progs)
    for h, title in HOL.items():
        v, u = cnt[(h, True)], cnt[(h, False)]
        if v or u:
            L.append(f"- **{title}**: проверено на сайте — {v}" + (f", не проверено — {u}" if u else ""))
    L += ["", "| ID | Каникулы | Провайдер | Программа | Возраст | Цена | Место | Для кого | Проверено |",
          "|---|---|---|---|---|---|---|---|---|"]
    aud = {"public": "все", "eligible": "HAF: по критериям", "university": "дети сотрудников и студентов университета"}
    for p in progs:
        L.append(f"| {p['id']} | {HOL[p['holiday']].split(' (')[0]} | {p['provider']} | {p['title']} | {p.get('ages') or '—'} | "
                 f"{p.get('price') or '—'} | {p.get('venue') or '—'} | {aud[p['audience']]} | {'да' if p.get('verified') else 'нет'} |")
    L += ["", "Не проверены (сайт закрыт для бота или без дат) — в выпуск не взяты:", ""]
    L += [f"- {n} — {why}" for n, _, why in kd["not_verified"]]
    L += ["", "Отброшены при проверке:", ""] + [f"- {n} — {why}" for n, why in kd["excluded"]] + [""]

    ru = (ROOT / "issues" / "issue_2026-10-01_v4_ru.md").read_text()
    m = re.search(r"\*\*Пунктов по рубрикам\*\*\n\n(.*?)\n\n", ru, re.S)
    cost = re.search(r"\*\*Расход Claude API на черновик\*\*\n\n- (.*?)\n", ru)
    hol = re.search(r"## Каникулы: куда записать ребёнка\n\n(.*?)(?=\n## )", ru, re.S)
    hol_n = {k: len(re.findall(r"^\*\*", part, re.M)) for k, part in
             zip(("october", "christmas"), re.split(r"^### Рождественские", hol.group(1), flags=re.M))} if hol else {}
    L += ["## Выпуск v4 (1–11 октября)", "",
          "`issues/issue_2026-10-01_v4_en.md`, `_ru.md` — с блоком «Для редактора»; `_v4_reader_en.html`, "
          "`_v4_reader_ru.html` — читательские версии без него (одна колонка «как письмо», светлая и тёмная тема, "
          "кликабельные ссылки); ответ модели — `_v4_model.json`.", "",
          "Пунктов по рубрикам:", "", m.group(1) if m else "—", ""]
    if hol_n:
        L += [f"В «Каникулах»: октябрьские — {hol_n.get('october', 0)}, рождественские — {hol_n.get('christmas', 0)}.", ""]

    am = json.loads((ROOT / "issues" / "issue_2026-10-01_v4_ai_measure.json").read_text())
    total = int(re.search(r"всего: (\d+)", m.group(1)).group(1)) if m else 0
    L += ["## Замер по ИИ-запретам (для решения на этапе 8)", "",
          f"Из {total} пунктов выпуска:",
          f"- только из источников с запретом `Claude-User` (Newsquest S116–S119) — **{len(am['only_claude_user_blocked'])}**"
          + (f": {'; '.join(am['only_claude_user_blocked'])}" if am['only_claude_user_blocked'] else "") + " → пропадут в режиме `claude_user_only`;",
          f"- только из источников с запретом ботов обучения/поиска (S003, S004, S010, S092, S093) — "
          f"**{len(am['only_training_blocked'])}**" + (f": {'; '.join(am['only_training_blocked'])}" if am['only_training_blocked'] else "") + ";",
          f"- в режиме `any_ai_agent` пропадут **{len(am['lost_any_ai_agent'])}** (всё, что пришло только из этих газет).", "",
          "Флаг `respect_ai_disallow` = `off` (режимы: off / claude_user_only / any_ai_agent).", ""]

    rows = con.execute("""SELECT purpose, model, count(*) n, sum(cost_usd) c FROM llm_usage WHERE called_at >= ?
        GROUP BY 1, 2 ORDER BY c DESC""", (STAGE_START,)).fetchall()
    L += ["## Расход Claude API на этап", "", "| Назначение | Модель | Запросов | $ |", "|---|---|---|---|"]
    L += [f"| {r['purpose']} | {r['model']} | {r['n']} | {r['c']:.4f} |" for r in rows]
    L += [f"| **итого** | | | **{sum(r['c'] for r in rows):.4f}** |", "",
          f"Выпуск: {cost.group(1) if cost else '—'}. Всего за проект: "
          f"${con.execute('SELECT sum(cost_usd) FROM llm_usage').fetchone()[0]:.2f}.", ""]
    (ROOT / "docs" / "stage6v4_report.md").write_text("\n".join(L).rstrip() + "\n")
    print("docs/stage6v4_report.md")


if __name__ == "__main__":
    main()
