# /// script
# dependencies = ["beautifulsoup4", "lxml"]
# ///
"""Turn cached NIST compilation-sheet HTML (data/raw_html) into ground-truth JSON.

Writes data/nist_gt.jsonl: one record per compilation sheet.

    source .venv/bin/activate && python parse_nist.py
"""
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

DATA = Path(__file__).parent / "data"
RAW = DATA / "raw_html"
P = "MainContentPlaceHolder_lbl_"
BASE = "https://srdata.nist.gov/solubility/"

FIELDS = {
    "original_measurements": "MeasValue",
    "variables": "VariValue",
    "prepared_by": "prepValue",
    # sheets without a table often give their values in these free-text fields
    "experimental_remarks": "ExpRValue",
    "experimental_data_text": "ExpDValue",
    "notes": "NoteValue",
    "method": "MethValue",
    "source_and_purity": "SrcValue",
    "estimated_errors": "ErrValue",
    "critical_evaluation_refs": "RefValue",
}
COMPONENT = re.compile(r"^\((\d+)\)\s*(.*?);\s*([^;]*?);\s*\[([^\]]*)\]")
NUMBER = re.compile(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$")


def text(el):
    """Plain text with <sup>/<sub> marked as ^ / _ and <br> as newlines."""
    if el is None:
        return None
    el = BeautifulSoup(str(el), "lxml")
    for t in el.find_all("sup"):
        t.replace_with(f"^{t.get_text()}" if t.get_text().strip() else "")
    for t in el.find_all("sub"):
        t.replace_with(f"_{t.get_text()}")
    for t in el.find_all("br"):
        t.replace_with("\n")
    s = el.get_text().replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in s.split("\n")]
    s = "\n".join(ln for ln in lines if ln)
    return s or None


def cell(s):
    s = (s or "").strip()
    if NUMBER.match(s):
        return float(s)
    return s or None


def parse_components(span):
    comps = []
    for line in (text(span) or "").split("\n"):
        line = line.replace("NIST Chemistry WebBook for detail", "").strip()
        m = COMPONENT.match(line)
        if m:
            comps.append({"index": int(m[1]), "name": m[2].strip(), "formula": m[3].strip() or None,
                          "cas": m[4].strip() or None})
        elif line:
            comps.append({"index": None, "name": line, "formula": None, "cas": None})
    return comps


def parse_tables(span):
    tables = []
    for t in span.find_all("table") if span else []:
        rows = t.find_all("tr")
        header = [text(c) for c in rows[0].find_all(["th", "td"])] if rows else []
        body = [[cell(text(c)) for c in r.find_all(["td", "th"])] for r in rows[1:]]
        tables.append({"caption": text(t.caption), "columns": header, "rows": body})
    return tables


def parse_sheet(html):
    soup = BeautifulSoup(html, "lxml")
    span = lambda k: soup.find(id=P + k)
    rec = {
        "system_name": text(span("SysName")),
        "components": parse_components(span("compValue")),
    }
    for key, sid in FIELDS.items():
        rec[key] = text(span(sid))
    rec["tables"] = parse_tables(span("Table"))
    return rec


def main():
    index = json.loads((DATA / "index.json").read_text())
    n, missing = 0, 0
    with open(DATA / "nist_gt.jsonl", "w") as out:
        for ds, vol in index.items():
            m = re.match(r"Volume\s+(\d+)\.\s*(.*)", vol["title"])
            volume = {"series_id": ds, "volume": int(m[1]) if m else None, "title": m[2] if m else vol["title"]}
            count = 0
            for system in vol["systems"]:
                for sh in system["sheets"]:
                    f = RAW / f"{sh['detail_id']}.html"
                    if not f.exists():
                        missing += 1
                        continue
                    rec = {"id": sh["detail_id"], "series_id": ds, "iupac_volume": volume["volume"],
                           "volume_title": volume["title"], "system_id": system["sys_id"],
                           "evaluated": sh["evaluated"],
                           "url": f"{BASE}sol_detail.aspx?goBack=Y&sysID={sh['detail_id']}",
                           "system_url": f"{BASE}sol_sys_lst.aspx?goBack=Y&sysID={system['sys_id']}&SerialID={ds}",
                           "volume_url": f"{BASE}sol_sys.aspx?nm_dataSeries={ds}",
                           **parse_sheet(f.read_text())}
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    count += 1
            print(f"{ds} vol {volume['volume']}: {count} sheets")
            n += count
    print(f"{n} records written, {missing} sheets not downloaded yet")


if __name__ == "__main__":
    main()
