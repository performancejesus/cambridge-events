"""56. Тема недели (исправляющая; правка 11 после v13): тема не повторяет тему отправленного выпуска за 8 недель (по
названию или основным событиям; черновики не считаются); в редакторской версии — 2–3 варианта темы с фразой «почему»
и событиями; выбор — за редактором (data/check_overrides.json → theme). build_issue.theme_choice.
Правка 11 после v14: в каникулярную неделю (и неделю перед каникулами) среди вариантов — сезонный (Хэллоуин и half-term),
если сезонных событий ≥ 4 (build_issue.seasonal_theme_option)."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 56, "Тема недели: без повтора 8 недель, 2–3 варианта для редактора", FIX


def check(ctx) -> Finding:
    from pipeline import history
    from scripts.build_issue import title_match
    f = Finding()
    theme = [it for rub, it in ctx.model_items() if rub == "theme"]
    ev = {e for it in theme for i in it["ids"] for e in (ctx.pools.candidates.get(i) or {}).get("event_ids", [])}
    for t in history.recent_themes(ctx.con, ctx.w.issue):
        if theme and (title_match(ctx.result.get("theme_title_en") or "", t["title_en"] or "") >= 0.6
                      or (ev and len(ev & set(t["event_ids"])) >= max(1, len(ev) // 2))):
            f.violations.append(f"тема «{ctx.result.get('theme_title_ru')}» повторяет выпуск от {t['issue_date']}")
    opts = ctx.result.get("theme_options") or []
    if theme and len(opts) < 2:
        f.warnings.append(f"вариантов темы для редактора: {len(opts)} (нужно 2–3)")
    from scripts.build_issue import SEASONAL_MIN, holiday_week, seasonal_candidates
    seas = seasonal_candidates(ctx.pools, ctx.w) if holiday_week(ctx.w) else []
    if len(seas) >= SEASONAL_MIN and not any(set(o.get("ids", [])) & set(seas) for o in opts):
        f.violations.append(f"каникулярная неделя ({holiday_week(ctx.w)}), сезонных событий {len(seas)}, "
                            f"а сезонного варианта темы нет")
    f.info.append(f"вариантов темы: {len(opts)}; тем отправленных выпусков за 8 недель: "
                  f"{len(history.recent_themes(ctx.con, ctx.w.issue))}")
    return f
