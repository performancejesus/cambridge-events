"""Этап 7c: обязательные проверки каждого выпуска (бриф, «Обязательные проверки каждого выпуска»).

Правило, записанное только в промпте, модель забывает (дата рождения Барретта: исправлено в v6, вернулось в v9). Поэтому
каждая принятая редакционная правка — проверка в коде. Один файл — одно правило: `rNN_<имя>.py` с полями
  RULE  — номер из брифа (1–28) или следующий свободный (29+, правки по v9 и новые рубрики);
  TITLE — короткое название (ru);
  LEVEL — BLOCK (выпуск нельзя отправлять: красная плашка «НЕ ОТПРАВЛЯТЬ» вверху редакторской версии) или
          FIX (ошибка исправляется при сборке без модели или одним коротким запросом; проверка — что не осталось);
  check(ctx) -> Finding — нарушения на готовом выпуске (структура пунктов + итоговые HTML).
Исправления делает сборка (scripts/build_issue.py) и записывает их в ctx.fix_log[RULE] — отсюда статус «исправлено».

Проверки запускаются при каждой сборке выпуска (build_issue) и отдельно: scripts/check_issue.py (так же проверен v9).
Проверки не удаляются и не отключаются без решения редактора.
"""

from __future__ import annotations

import importlib
import json
import pkgutil
from dataclasses import dataclass, field
from pathlib import Path

BLOCK, FIX = "block", "fix"
LEVEL_RU = {BLOCK: "блокирующая", FIX: "исправляющая"}
STATUS_RU = {"pass": "прошла", "fixed": "исправлено", "block": "блокирует", "left": "осталось — редактору",
             "warn": "замечание", "skip": "не проверялась"}


@dataclass
class Finding:
    violations: list[str] = field(default_factory=list)   # BLOCK → блок; FIX → осталось после исправления
    warnings: list[str] = field(default_factory=list)     # не блокирует: редактору
    skipped: str | None = None                            # проверка не выполнялась (нет сети, нет ключа) — почему
    info: list[str] = field(default_factory=list)         # что проверено (для отчёта)


@dataclass
class Outcome:
    rule: int
    title: str
    level: str
    status: str                       # pass | fixed | block | left | warn | skip
    details: list[str]
    fixed: list[str]

    def as_dict(self) -> dict:
        return {"rule": self.rule, "title": self.title, "level": self.level, "status": self.status,
                "details": self.details, "fixed": self.fixed}


def rules() -> list:
    mods = []
    for m in pkgutil.iter_modules([str(Path(__file__).parent)]):
        if m.name.startswith("r") and m.name[1:3].isdigit():
            mods.append(importlib.import_module(f"{__name__}.{m.name}"))
    return sorted(mods, key=lambda m: m.RULE)


def run(ctx) -> list[Outcome]:
    out = []
    for m in rules():
        try:
            f = m.check(ctx)
        except Exception as e:  # noqa: BLE001 — упавшая проверка не должна молча пропускать выпуск
            f = Finding(violations=[f"проверка упала: {type(e).__name__}: {e}"] if m.LEVEL == BLOCK else [],
                        warnings=[] if m.LEVEL == BLOCK else [f"проверка упала: {type(e).__name__}: {e}"])
        fixed = [ru for _, ru in ctx.fix_log.get(m.RULE, [])]
        if f.skipped and not f.violations:
            status = "skip"
        elif f.violations:
            status = "block" if m.LEVEL == BLOCK else "left"
        elif fixed:
            status = "fixed"
        elif f.warnings:
            status = "warn"
        else:
            status = "pass"
        details = f.violations + f.warnings + ([f"не проверялась: {f.skipped}"] if f.skipped else [])
        out.append(Outcome(m.RULE, m.TITLE, m.LEVEL, status, details, fixed))
    return out


def blocking(outcomes: list[Outcome], per_rule: int = 4, width: int = 260) -> list[str]:
    """Причины блокировки: по каждому правилу — до per_rule первых, длинные — обрезаны (полностью — в таблице проверок)."""
    out = []
    for o in outcomes:
        if o.status != "block":
            continue
        ds = [d for d in o.details if not d.startswith("не проверялась") and "не проверить" not in d]
        out += [f"{o.rule}. {o.title}: " + (d if len(d) <= width else d[:width - 1] + "…") for d in ds[:per_rule]]
        if len(ds) > per_rule:
            out.append(f"{o.rule}. {o.title}: … и ещё {len(ds) - per_rule}")
    return out


def save(outcomes: list[Outcome], path: Path, issue_date: str, version: str) -> dict:
    """issues/<выпуск>_checks.json — для отчёта и для этапа 8: send_allowed=false, пока есть блокирующие."""
    data = {"issue_date": issue_date, "version": version, "send_allowed": not blocking(outcomes),
            "blocking": blocking(outcomes), "checks": [o.as_dict() for o in outcomes]}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    return data


def plate_html(outcomes: list[Outcome], lang: str) -> str:
    """Красная плашка вверху редакторской версии: «НЕ ОТПРАВЛЯТЬ: …» со списком причин; зелёная — если можно."""
    from html import escape as e
    reasons = blocking(outcomes)
    if not reasons:
        ok = ("All blocking checks passed — the issue may be sent after the editor's read."
              if lang == "en" else "Все блокирующие проверки пройдены — выпуск можно отправлять после вычитки.")
        return f'<div class="plate ok">{e(ok)}</div>'
    head = "DO NOT SEND" if lang == "en" else "НЕ ОТПРАВЛЯТЬ"
    return (f'<div class="plate stop"><b>{head}:</b><ul>' + "".join(f"<li>{e(r)}</li>" for r in reasons)
            + "</ul></div>")


def table_rows(outcomes: list[Outcome], lang: str = "ru") -> list[str]:
    """Строки «проверка → уровень → результат» для блока «Для редактора»."""
    rows = []
    for o in outcomes:
        tail = "; ".join((o.details + o.fixed)[:6])
        more = len(o.details + o.fixed) - 6
        rows.append(f"{o.rule}. {o.title} — {LEVEL_RU[o.level]} — {STATUS_RU[o.status]}"
                    + (f": {tail}" if tail else "") + (f" … (+{more})" if more > 0 else ""))
    return rows


PLATE_CSS = """.plate { border-radius:8px; padding:12px 14px; margin:0 0 18px;
  font:14px/1.45 -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }
.plate.stop { background:#b3261e; color:#fff; } .plate.stop ul { margin:6px 0 0; padding-left:18px; }
.plate.ok { background:#e3f1e5; color:#1d4d27; }
@media (prefers-color-scheme: dark) { .plate.ok { background:#1f3524; color:#cfe8d3; } }"""
