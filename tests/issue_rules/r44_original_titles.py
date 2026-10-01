"""44. Названия событий — в оригинале (исправляющая; этап 7e, правки по v11: «Три ура Винни-Пуху! Сказочная тропа» —
это «Three Cheers for Pooh!» в Anglesey Abbey). В русской версии заголовок события, анонса, отмены, фильма — как в
данных (латиницей); перевод можно дать в описании. Исправляет issue_fixes.fix_original_titles."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 44, "Названия событий — в оригинале, перевод — в описании", FIX


def check(ctx) -> Finding:
    from pipeline.issue_fixes import CYR_RE, ORIGINAL_KINDS
    f = Finding()
    for rub, it in ctx.model_items():
        cs = [ctx.pools.candidates[i] for i in it["ids"] if i in ctx.pools.candidates]
        if not cs or cs[0]["kind"] not in ORIGINAL_KINDS or len(it["ids"]) > 3 or it.get("union"):
            continue
        if CYR_RE.search(it.get("title_ru") or "") and not CYR_RE.search(it.get("title_en") or ""):
            f.violations.append(f"«{it['title_ru']}»: перевод вместо оригинального названия «{it['title_en']}»")
    return f
