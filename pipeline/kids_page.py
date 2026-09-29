"""Решения после 6c: полный список программ на каникулы — отдельная страница kids_<каникулы>_<год>_<ru|en>.html рядом
с выпуском (в письме — строка «Ещё N программ на эти каникулы →»). Все проверенные программы в зонах выпуска, фильтр
по возрасту ребёнка и по зоне (скрипт на странице, без внешних библиотек). Пока локальный файл; публикация — этап 8.
"""

from __future__ import annotations

import re
from html import escape

from . import issue

ZONES_EN = {"центр": "Cambridge", "до 30 мин": "within 30 min", "до часа": "within an hour",
            "Кембриджшир, дальше часа": "Cambridgeshire, over an hour"}
ZONES_RU = {"центр": "Кембридж", "до 30 мин": "до 30 мин", "до часа": "до часа",
            "Кембриджшир, дальше часа": "Кембриджшир, дальше часа"}


def age_range(ages: str | None) -> tuple[int, int]:
    """«5-14», «4 to 14 years», «Years 3-9» (Year N ≈ N+5 лет), «Reception - 12» (Reception ≈ 4) → (от, до); нет — (0, 99)."""
    a = (ages or "").lower()
    if not a:
        return 0, 99
    a = re.sub(r"reception", "4", a)
    yrs = re.findall(r"years? (\d+)", a)
    if yrs:
        nums = [int(y) + 5 for y in yrs]
        more = re.findall(r"(?:[-–]|to)\s*(?:year )?(\d+)", a)
        if more and not re.search(r"year \d+\s*(?:[-–]|to)\s*year", a):
            nums.append(int(more[-1]) + 5)
        return min(nums), max(nums) + 1
    nums = [int(n) for n in re.findall(r"\d+", a) if int(n) < 19]
    if not nums:
        return 0, 99
    if "+" in a or "over" in a:
        return nums[0], 99
    return min(nums), max(nums)


def render(p: "issue.Pools", w: "issue.Window", lang: str, hol: str, h: dict) -> str:
    groups = issue.programme_lines(p, w, lang)
    pairs = groups.get(hol, []) + [xl for xl in groups.get("hurry", []) if xl[0]["c"]["holiday"] == hol]
    zones = ZONES_EN if lang == "en" else ZONES_RU
    title = (f"{issue.HOLIDAY_TITLES[hol]['en']}: all programmes" if lang == "en" else
             f"{issue.HOLIDAY_TITLES[hol]['ru']}: все программы")
    rng = f"{issue._day(issue.d(h['start']), lang, weekday=False)} – {issue._day(issue.d(h['end']), lang, weekday=False)}"
    rows = []
    for x, ln in sorted(pairs, key=lambda xl: (xl[0]["zone"], xl[1]["title"].lower())):
        lo, hi = age_range(x["c"].get("ages"))
        z = x["c"].get("zone") or ""
        rows.append(f'<li data-lo="{lo}" data-hi="{hi}" data-zone="{escape(z)}"><a href="{escape(ln["url"] or "#")}">'
                    f'{escape(ln["title"])}</a><div class="meta">{escape(ln["meta"])}'
                    f'{" · " + escape(zones.get(z, z)) if z else ""}</div></li>')
    zone_opts = "".join(f'<option value="{escape(k)}">{escape(v)}</option>' for k, v in zones.items())
    t = {"age": "Child's age" if lang == "en" else "Возраст ребёнка",
         "zone": "Zone" if lang == "en" else "Зона", "all": "all" if lang == "en" else "все",
         "count": "programmes" if lang == "en" else "программ",
         "note": ("Verified on the providers' websites. Check dates and prices when booking." if lang == "en" else
                  "Проверено на сайтах провайдеров. Даты и цены уточняйте при записи.")}
    return f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>
:root {{ --bg:#fbfaf7; --fg:#1d1b18; --muted:#6b645a; --line:#e4dfd6; --accent:#8a3b12; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#1b1a18; --fg:#ece8e1; --muted:#a39b8f; --line:#3a3631; --accent:#e0915f; }} }}
body {{ background:var(--bg); color:var(--fg); font:16px/1.5 Georgia, serif; margin:0; padding:16px; }}
main {{ max-width:720px; margin:0 auto; }}
h1 {{ color:var(--accent); font-size:1.5rem; margin:.2rem 0; }}
.sub, .meta, label {{ color:var(--muted); font:14px/1.4 -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }}
.filters {{ display:flex; flex-wrap:wrap; gap:12px; margin:12px 0; }}
select, input {{ font:inherit; max-width:100%; }}
ul {{ list-style:none; padding:0; }} li {{ border-top:1px solid var(--line); padding:8px 0; }}
a {{ color:var(--fg); font-weight:bold; }}
</style></head><body><main>
<h1>{escape(title)}</h1><div class="sub">{escape(rng)} · <span id="n">{len(rows)}</span> {t['count']}</div>
<p class="sub">{t['note']}</p>
<div class="filters"><label>{t['age']}: <input id="age" type="number" min="0" max="18" inputmode="numeric" style="width:4em"></label>
<label>{t['zone']}: <select id="zone"><option value="">{t['all']}</option>{zone_opts}</select></label></div>
<ul id="list">{''.join(rows)}</ul>
<script>
function f(){{var a=parseInt(document.getElementById('age').value),z=document.getElementById('zone').value,n=0;
document.querySelectorAll('#list li').forEach(function(li){{var ok=(isNaN(a)||(a>=+li.dataset.lo&&a<=+li.dataset.hi))&&(!z||li.dataset.zone===z);
li.style.display=ok?'':'none';if(ok)n++;}});document.getElementById('n').textContent=n;}}
document.getElementById('age').addEventListener('input',f);document.getElementById('zone').addEventListener('change',f);
</script></main></body></html>
"""
