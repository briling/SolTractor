"""Unpack a node hand-back (page pass and crop pass of one volume) into the repository layout.

Usage: python3 -I scripts/unpack_node.py SDS-N [--raw /path/to/library/mineru/SDS-N]
       python3 -I scripts/unpack_node.py SDS-N --crops crops-v2 --raw /path/to/library/mineru/crops-v2/SDS-N

The node returns one folder per volume in the HU Box library: SDS-N.zip (page pass),
crops-out.zip (one zip per crop), SDS-N.page.log, SDS-N.crops.log, SDS-N.manifest.csv
and handback.md. That folder is linked as data/.../mineru/SDS-N/raw (ignored by git;
`--raw` creates the link). This script writes next to it what the converters need:
structured_content.json and middle_json.json of the page pass, run.log, handback.md,
crops/manifest.csv, crops/run.log and crops/tables.jsonl, one line per crop with the
blocks MinerU returned, read straight from the per-crop zips without extracting their
images. Then run mineru_to_boxes.py, crops_to_boxes.py and align_nist.py as in README.md.

With --crops NAME the hand-back is a crop pass alone (a second run on new bands): its
crops-out.zip, manifest, log and handback.md are unpacked into mineru/SDS-N/NAME/ next to
the first run, which stays untouched; then crops_to_boxes.py boxes-page.jsonl NAME/tables.jsonl
boxes-NAME.jsonl, and check_rows.py, align_nist.py and to_nomad.py on that boxes file.
"""
import argparse, io, json, pathlib, shutil, sys, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from paths import volume_root  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('volume')
    ap.add_argument('--raw', type=pathlib.Path, help='node folder to link as raw/ if the link does not exist yet')
    ap.add_argument('--crops', metavar='NAME', help='unpack a crop-pass-only hand-back into mineru/SDS-N/NAME/')
    a = ap.parse_args()
    vol = a.volume if a.volume.startswith('SDS-') else f'SDS-{a.volume}'
    out = volume_root(vol) / 'mineru' / vol
    out.mkdir(parents=True, exist_ok=True)
    if a.crops:
        if not a.raw:
            sys.exit('--crops needs --raw <node folder of this crop run>')
        raw, crops_dir = a.raw, out / a.crops
        crops_dir.mkdir(exist_ok=True)
        for src, dst in ((f'{vol}.crops.log', 'run.log'), ('handback.md', 'handback.md'), (f'{vol}.manifest.csv', 'manifest.csv'), ('manifest.csv', 'manifest.csv')):
            if (raw / src).exists():
                shutil.copy(raw / src, crops_dir / dst)
    else:
        raw = out / 'raw'
        if not raw.exists():
            if not a.raw:
                sys.exit(f'{raw} missing; pass --raw <library folder of {vol}>')
            raw.symlink_to(a.raw.resolve())
        crops_dir = out / 'crops'
        crops_dir.mkdir(exist_ok=True)
        with zipfile.ZipFile(raw / f'{vol}.zip') as z:
            for name in ('structured_content.json', 'middle_json.json'):
                member = next(n for n in z.namelist() if n.endswith(name))
                (out / name).write_bytes(z.read(member))
        for src, dst in ((f'{vol}.page.log', 'run.log'), ('handback.md', 'handback.md'),
                         (f'{vol}.crops.log', 'crops/run.log'), (f'{vol}.manifest.csv', 'crops/manifest.csv')):
            if (raw / src).exists():
                shutil.copy(raw / src, out / dst)

    n_crops, n_tables = 0, 0
    with zipfile.ZipFile(raw / 'crops-out.zip') as outer, (crops_dir / 'tables.jsonl').open('w') as f:
        for name in sorted(outer.namelist()):
            if not name.endswith('.zip'):
                continue
            with zipfile.ZipFile(io.BytesIO(outer.read(name))) as inner:
                member = next((n for n in inner.namelist() if n.endswith('structured_content.json')), None)
                if member is None:
                    continue
                doc = json.loads(inner.read(member))
            blocks = [b for p in doc['pages'] for b in p['blocks']]
            n_crops += 1
            n_tables += any(b['type'] == 'table' for b in blocks)
            f.write(json.dumps({'crop': pathlib.Path(name).stem + '.png', 'blocks': blocks}, ensure_ascii=False) + '\n')
    print(f'{vol}: {"crop pass" if a.crops else "page pass and crop pass"} unpacked, {n_crops} crops ({n_tables} with a table) -> {crops_dir if a.crops else out}')


main()
