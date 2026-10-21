# /// script
# dependencies = ["requests", "beautifulsoup4", "lxml"]
# ///
"""Crawl the IUPAC-NIST Solubility Database (https://srdata.nist.gov/solubility/).

Hierarchy: volume (DSn) -> system (sol_sys_lst) -> compilation sheet (sol_detail).
Stage 1 builds data/index.json, stage 2 caches every detail page under data/raw_html/.
Both stages are resumable; re-running only fetches what is missing.

    source .venv/bin/activate && python scrape_nist.py
"""
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://srdata.nist.gov/solubility/"
DATA = Path(__file__).parent / "data"
RAW = DATA / "raw_html"
INDEX = DATA / "index.json"
GRID = "ctl00$MainContentPlaceHolder$GridView1"
WORKERS = 4
DELAY = 0.2

_local = threading.local()


def session():
    if not hasattr(_local, "s"):
        _local.s = requests.Session()
        _local.s.headers["User-Agent"] = "Mozilla/5.0 (IUPAC-SDS hackathon research crawler)"
    return _local.s


def get(url, data=None, tries=5):
    for i in range(tries):
        try:
            s = session()
            r = s.post(url, data=data, timeout=60) if data else s.get(url, timeout=60)
            r.raise_for_status()
            time.sleep(DELAY)
            return r.text
        except requests.RequestException as e:
            print(f"  retry {i + 1} {url}: {e}")
            time.sleep(2 ** i)
    raise RuntimeError(f"failed: {url}")


def all_grid_pages(url):
    """Yield soup for every page of an ASP.NET GridView (pages are postbacks)."""
    soup = BeautifulSoup(get(url), "lxml")
    yield soup
    pages = sorted({int(p) for p in re.findall(r"Page\$(\d+)", str(soup))} - {1})
    for p in pages:
        form = {i["name"]: i.get("value", "") for i in soup.select("input[type=hidden]") if i.get("name")}
        form["__EVENTTARGET"], form["__EVENTARGUMENT"] = GRID, f"Page${p}"
        yield BeautifulSoup(get(url, data=form), "lxml")


def list_sheets(link):
    sys_url = link["href"]
    system = {"sys_id": re.search(r"sysID=(\d+)", sys_url).group(1),
              "name": link.get_text(strip=True), "sheets": []}
    # each thread needs its own session: ASP.NET postbacks are stateful
    for sp in all_grid_pages(BASE + sys_url):
        for d in sp.select("a[href*=sol_detail]"):
            row = d.find_parent("tr")
            system["sheets"].append({
                "detail_id": re.search(r"sysID=([\w]+)", d["href"]).group(1),
                # the "Evaluated?" column is a disabled checkbox
                "evaluated": bool(row and row.select_one("input[type=checkbox][checked]")),
            })
    return system


def build_index():
    index = json.loads(INDEX.read_text()) if INDEX.exists() else {}
    soup = BeautifulSoup(get(BASE + "dataSeries.aspx"), "lxml")
    for a in soup.select("a[href*=nm_dataSeries]"):
        ds = a["href"].split("=")[-1]
        if index.get(ds, {}).get("done"):
            continue
        vol = {"series_id": ds, "title": a.get_text(strip=True)}
        print(f"{ds}: {vol['title']}", flush=True)
        links = [s for page in all_grid_pages(BASE + a["href"]) for s in page.select("a[href*=sol_sys_lst]")]
        with ThreadPoolExecutor(WORKERS) as ex:
            vol["systems"] = list(ex.map(list_sheets, links))
        vol["done"] = True
        index[ds] = vol
        INDEX.write_text(json.dumps(index, indent=1))
        n = sum(len(s["sheets"]) for s in vol["systems"])
        print(f"  {len(vol['systems'])} systems, {n} sheets", flush=True)
    return index


def fetch_detail(detail_id):
    out = RAW / f"{detail_id}.html"
    if not out.exists():
        out.write_text(get(f"{BASE}sol_detail.aspx?goBack=Y&sysID={detail_id}"))


def main():
    DATA.mkdir(exist_ok=True)
    RAW.mkdir(exist_ok=True)
    index = build_index()
    ids = sorted({sh["detail_id"] for v in index.values() for s in v["systems"] for sh in s["sheets"]})
    todo = [i for i in ids if not (RAW / f"{i}.html").exists()]
    print(f"{len(ids)} sheets total, {len(todo)} to download")
    with ThreadPoolExecutor(WORKERS) as ex:
        for k, _ in enumerate(ex.map(fetch_detail, todo), 1):
            if k % 200 == 0:
                print(f"  {k}/{len(todo)}", flush=True)


if __name__ == "__main__":
    main()
