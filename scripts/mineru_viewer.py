"""Side-by-side viewer for one MinerU 4 output: each table crop next to its extracted HTML.

    python3 -I mineru_viewer.py <extracted-dir> <out.html> [title]

Reads <extracted-dir>/middle_json.json and links the crops in <extracted-dir>/images by absolute file:// path.
The table HTML is re-emitted through a whitelist (table/tr/td/th, colspan/rowspan); everything else is escaped.
"""

import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

NUM = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?(?![\w])")
WORD = re.compile(r"[A-Za-z]{3,}")
RUNON = re.compile(r"\b\d+\.\d{4,}\b")  # e.g. 1.1410 = 1.14 + next row's 10
KEEP = {"table", "thead", "tbody", "tr", "td", "th"}


class Clean(HTMLParser):
    """Whitelist re-emitter; also collects the text of each cell."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.cells, self.cell = [], [], None

    def handle_starttag(self, tag, attrs):
        if tag in KEEP:
            keep = "".join(f' {k}="{int(v)}"' for k, v in attrs if k in ("colspan", "rowspan") and (v or "").isdigit())
            self.out.append(f"<{tag}{keep}>")
            if tag in ("td", "th"):
                self.cell = []
        elif tag == "eq":
            self.out.append('<code class="eq">')

    def handle_endtag(self, tag):
        if tag in KEEP:
            self.out.append(f"</{tag}>")
            if tag in ("td", "th") and self.cell is not None:
                self.cells.append(" ".join(self.cell))
                self.cell = None
        elif tag == "eq":
            self.out.append("</code>")

    def handle_data(self, data):
        self.out.append(html.escape(data))
        if self.cell is not None:
            self.cell.append(data)


def assess(cells: list[str]) -> tuple[str, str]:
    numeric_cells = [c for c in cells if NUM.search(c)]
    worst = max(cells, key=lambda c: len(NUM.findall(c)), default="")
    n, w = len(NUM.findall(worst)), len(WORD.findall(worst))
    runon = sorted({m for c in cells for m in RUNON.findall(c)})
    if n >= 8 and n > 1.5 * w:
        return "suspect", f"one cell holds {n} numbers" + (f"; run-together? {', '.join(runon[:4])}" if runon else "")
    if len(numeric_cells) >= 6:
        return "clean", f"{len(numeric_cells)} numeric cells"
    return "other", "few numbers"


def main() -> None:
    src, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
    title = sys.argv[3] if len(sys.argv) > 3 else src.parent.name
    m = json.loads((src / "middle_json.json").read_text())
    cards, counts = [], {"suspect": 0, "clean": 0, "other": 0}
    for p in m["pages"]:
        for b in p["blocks"]:
            if b["type"] != "table":
                continue
            for body in (c for c in b.get("content", []) if c.get("type") == "table_body"):
                parser = Clean()
                parser.feed(body.get("content", ""))
                kind, why = assess(parser.cells)
                counts[kind] += 1
                img = src / body["image_path"] if body.get("image_path") else None
                page = p["page_idx"] + 1
                cards.append(
                    f'<section class="card {kind}" data-page="{page}" tabindex="-1">'
                    f'<header><b>p. {page}</b> <span class="badge {kind}">{kind}</span> <span class="why">'
                    f'{html.escape(why)}</span>{" <span class=cont>continues previous</span>" if b.get("continues_prev") else ""}'
                    f"</header><div class=pair>"
                    + (f'<a href="{img.as_uri()}" target="_blank"><img loading="lazy" src="{img.as_uri()}" alt="scan crop, page {page}"></a>'
                       if img and img.exists() else "<div class=noimg>no crop</div>")
                    + f'<div class="extracted">{"".join(parser.out)}</div></div></section>'
                )
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>MinerU tables {html.escape(title)}</title>
<style>
:root {{ --bg:#fafaf9; --fg:#1c1917; --muted:#78716c; --line:#d6d3d1; --card:#fff;
  --suspect:#b45309; --clean:#15803d; --other:#57534e; --eq:#f5f5f4; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#1c1917; --fg:#e7e5e4; --muted:#a8a29e; --line:#44403c;
  --card:#292524; --suspect:#f59e0b; --clean:#4ade80; --other:#a8a29e; --eq:#44403c; }} }}
* {{ box-sizing:border-box }} body {{ margin:0; background:var(--bg); color:var(--fg); font:14px/1.45 system-ui,sans-serif }}
nav {{ position:sticky; top:0; z-index:1; background:var(--bg); border-bottom:1px solid var(--line); padding:10px 16px;
  display:flex; gap:8px; flex-wrap:wrap; align-items:center }}
nav h1 {{ font-size:16px; margin:0 12px 0 0 }} nav button {{ font:inherit; padding:4px 10px; border:1px solid var(--line);
  background:var(--card); color:var(--fg); border-radius:6px; cursor:pointer }} nav button[aria-pressed=true] {{ border-color:var(--fg) }}
nav input {{ font:inherit; width:7em; padding:4px 6px; border:1px solid var(--line); background:var(--card); color:var(--fg); border-radius:6px }}
nav .hint {{ color:var(--muted); margin-left:auto }}
main {{ padding:16px; display:grid; gap:16px }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:12px; outline:none }}
.card:focus {{ border-color:var(--fg) }} .card header {{ margin-bottom:8px }} .why,.cont {{ color:var(--muted); margin-left:6px }}
.badge {{ font-size:12px; padding:1px 6px; border-radius:4px; border:1px solid currentColor }}
.badge.suspect {{ color:var(--suspect) }} .badge.clean {{ color:var(--clean) }} .badge.other {{ color:var(--other) }}
.pair {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:12px; align-items:start }}
@media (max-width:800px) {{ .pair {{ grid-template-columns:1fr }} }}
.pair img {{ width:100%; border:1px solid var(--line); background:#fff }}
.extracted {{ overflow-x:auto }} .extracted table {{ border-collapse:collapse; font-size:12px }}
.extracted td,.extracted th {{ border:1px solid var(--line); padding:2px 5px; vertical-align:top }}
code.eq {{ background:var(--eq); border-radius:3px; padding:0 2px; font-size:11px }}
.hidden {{ display:none }}
</style></head><body>
<nav><h1>{html.escape(title)}: {len(cards)} tables</h1>
<button data-f="all" aria-pressed="true">all</button>
<button data-f="suspect">suspect ({counts['suspect']})</button>
<button data-f="clean">clean-looking ({counts['clean']})</button>
<button data-f="other">few numbers ({counts['other']})</button>
<input id="pg" type="number" min="1" placeholder="page" aria-label="jump to page">
<span class="hint">j / k: next / previous · click a scan to open it full size</span></nav>
<main>{"".join(cards)}</main>
<script>
const cards = [...document.querySelectorAll('.card')];
let filter = 'all', cur = -1;
const visible = () => cards.filter(c => !c.classList.contains('hidden'));
document.querySelectorAll('nav button').forEach(b => b.onclick = () => {{
  filter = b.dataset.f;
  document.querySelectorAll('nav button').forEach(x => x.setAttribute('aria-pressed', x === b));
  cards.forEach(c => c.classList.toggle('hidden', filter !== 'all' && !c.classList.contains(filter)));
  cur = -1;
}});
document.getElementById('pg').onchange = e => {{
  const c = visible().find(c => +c.dataset.page >= +e.target.value);
  if (c) {{ c.focus(); c.scrollIntoView({{block:'start'}}); cur = visible().indexOf(c); }}
}};
document.addEventListener('keydown', e => {{
  if (e.target.tagName === 'INPUT' || !'jk'.includes(e.key)) return;
  const v = visible(); if (!v.length) return;
  cur = Math.max(0, Math.min(v.length - 1, cur + (e.key === 'j' ? 1 : -1)));
  v[cur].focus(); v[cur].scrollIntoView({{block:'start'}});
}});
</script></body></html>"""
    out.write_text(doc)
    print(f"{out}: {len(cards)} tables, {counts}")


if __name__ == "__main__":
    main()
