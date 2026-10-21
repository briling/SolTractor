"""Cut the OCR text of an SDS volume into data sheets and their form boxes.

Usage: python -I segment_boxes.py SDS-N [--out boxes/SDS-N.jsonl] [--stats]

Every compilation sheet of the series is a fixed form: a two-column header
(COMPONENTS | ORIGINAL MEASUREMENTS, VARIABLES | PREPARED BY), a full-width
EXPERIMENTAL VALUES box, and a two-column AUXILIARY INFORMATION block
(METHOD / APPARATUS/PROCEDURE | SOURCE AND PURITY OF MATERIALS / ESTIMATED
ERROR / REFERENCES). Evaluation sheets have COMPONENTS | EVALUATOR and a
full-width CRITICAL EVALUATION. A page may hold several sheets, and a sheet
may continue on the next page (header repeated, "(continued)").

The boxes are located by their printed headers (matched fuzzily, since the OCR
layer garbles them: COHPONENTS, AUXI LIARY, ESTIMATED ERRORS) and two-column
regions are split at the character column where the right-hand header starts.
Output is one JSON record per sheet with the raw text of each box, so later
stages (alignment with the NIST database, LLM extraction, back-search QC)
work box by box instead of on flat page text.
"""
import argparse, collections, json, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from paths import volume_root  # noqa: E402

CONFUSE = {'M': '[MH]', 'O': '[O0]', 'I': '[I1l|]', 'L': '[L1]', 'S': '[S5]', 'B': '[B8]', 'E': '[E3]', 'U': '[UV]'}


def fuzzy(phrase: str) -> re.Pattern:
    parts = []
    for ch in phrase:
        if ch == ' ':
            parts.append(r'\s*')
        else:
            parts.append(CONFUSE.get(ch, re.escape(ch)) + r'\s?')
    return re.compile(''.join(parts), re.I)


M = {k: fuzzy(v) for k, v in {
    'components': 'COMPONENTS', 'original': 'ORIGINAL MEASUREMENTS', 'evaluator': 'EVALUATOR',
    'variables': 'VARIABLES', 'prepared': 'PREPARED BY', 'experimental': 'EXPERIMENTAL VALUES',
    'critical': 'CRITICAL EVALUATION', 'auxiliary': 'AUXILIARY INFORMATION',
    'method': 'METHOD', 'apparatus': 'APPARATUS', 'source': 'SOURCE AND PURITY',
    'error': 'ESTIMATED ERROR', 'references': 'REFERENCES',
}.items()}


def find(lines: list[str], key: str, start: int = 0, end: int | None = None) -> tuple[int, int] | None:
    """(line index, column) of the first line in [start, end) that holds the marker."""
    for i in range(start, len(lines) if end is None else end):
        m = M[key].search(lines[i])
        if m:
            return i, m.start()
    return None


HEADER = re.compile(r'^\s*[^a-z\d]{3,45}?:\s*')


def strip_header(line: str) -> str:
    """Remove a printed box header ("SOURCE AND PURITY OF MATERIALS:") from the start of a line."""
    return HEADER.sub('', line, count=1) if HEADER.match(line) else line


def strip_block(lines: list[str]) -> str:
    text = '\n'.join(l.rstrip() for l in lines)
    return re.sub(r'\n{3,}', '\n\n', text).strip('\n')


def split_columns(lines: list[str], col: int) -> tuple[list[str], list[str]]:
    return [l[:col] for l in lines], [l[col:] for l in lines]


def cut_marker(lines: list[str], keys: list[str]) -> dict[str, str]:
    """Split a single-column run of lines into boxes at the given marker headers (in order)."""
    pos, seen = [], set()
    for k in keys:
        hit = find(lines, k)
        if hit and hit[0] not in seen:          # METHOD/APPARATUS/PROCEDURE is one header
            pos.append((hit[0], k)); seen.add(hit[0])
    pos.sort()
    out = {}
    for n, (i, k) in enumerate(pos):
        j = pos[n + 1][0] if n + 1 < len(pos) else len(lines)
        out[k] = strip_block([strip_header(lines[i])] + lines[i + 1:j])
    if pos and pos[0][0] > 0:
        out['_before'] = strip_block(lines[:pos[0][0]])
    return out


def parse_sheet(lines: list[str]) -> dict:
    """lines start at the COMPONENTS header line."""
    boxes, flags = {}, []
    head = lines[0]
    right = find([head], 'original') or find([head], 'evaluator')
    kind = 'compilation' if (right and M['original'].search(head)) else 'evaluation' if right else 'unknown'
    col = right[1] if right else None
    var = find(lines, 'variables', 1)
    exp = find(lines, 'experimental', 1)
    crit = find(lines, 'critical', 1)
    aux = find(lines, 'auxiliary', 1)
    body_start = (exp or crit or (None, None))[0]
    if var and body_start is not None and var[0] >= body_start:
        var = None                                   # "VARIABLES" inside the table, not a box header
    if aux and body_start is not None and aux[0] <= body_start:
        aux = None                                   # stray "AUXILIARY INFORMATION" before the table
    # header block: COMPONENTS | ORIGINAL MEASUREMENTS / EVALUATOR
    h_end = var[0] if var else body_start if body_start else len(lines)
    top = lines[:h_end]
    if col:
        l, r = split_columns(top, col)
        l[0], r[0] = strip_header(l[0]), strip_header(r[0])
        boxes['components'] = strip_block(l)
        boxes['original_measurements' if kind == 'compilation' else 'evaluator'] = strip_block(r)
    else:
        boxes['components'] = strip_block([strip_header(top[0])] + top[1:]); flags.append('no_right_header')
    # VARIABLES | PREPARED BY
    if var:
        v_end = body_start if body_start else len(lines)
        blk = lines[var[0]:v_end]
        pb = find([blk[0]], 'prepared')
        c2 = pb[1] if pb else col
        if c2:
            l, r = split_columns(blk, c2)
            l[0], r[0] = strip_header(l[0]), strip_header(r[0])
            boxes['variables'], boxes['prepared_by'] = strip_block(l), strip_block(r)
        else:
            boxes['variables'] = strip_block(blk); flags.append('no_prepared_by')
    elif kind == 'compilation':
        flags.append('no_variables')
    # EXPERIMENTAL VALUES / CRITICAL EVALUATION (full width)
    continued = False
    if body_start is not None:
        b_end = aux[0] if aux else len(lines)
        blk = lines[body_start:b_end]
        key = 'experimental_values' if exp else 'critical_evaluation'
        first = strip_header(blk[0])
        continued = bool(re.search(r'\(\s*cont', first, re.I))
        boxes[key] = strip_block([first] + blk[1:])
    else:
        flags.append('no_body')
    # AUXILIARY INFORMATION: METHOD/APPARATUS | SOURCE AND PURITY / ESTIMATED ERROR / REFERENCES
    if aux:
        blk = lines[aux[0] + 1:]
        src = find(blk, 'source')
        c3 = src[1] if src else col
        if c3:
            l, r = split_columns(blk, c3)
            lb = cut_marker(l, ['method', 'apparatus'])
            rb = cut_marker(r, ['source', 'error', 'references'])
            boxes['method'] = '\n'.join(filter(None, [lb.get('method', ''), lb.get('apparatus', '')])).strip()
            if 'apparatus' in lb:
                boxes['apparatus_procedure'] = lb['apparatus']
            boxes['source_purity'] = rb.get('source', '')
            boxes['estimated_error'] = rb.get('error', '')
            boxes['references'] = rb.get('references', '')
            if not src: flags.append('no_source_header')
        else:
            boxes['auxiliary'] = strip_block(blk); flags.append('aux_unsplit')
    elif kind == 'compilation' and not continued:
        flags.append('no_auxiliary')
    return {'kind': kind, 'continued': continued, 'col_header': col, 'boxes': boxes, 'flags': flags}


def segment(volume: str) -> list[dict]:
    pages = (volume_root(volume) / 'text' / f'{volume}.txt').read_text(errors='replace').split('\f')
    out = []
    for pno, page in enumerate(pages, 1):
        lines = page.split('\n')
        starts = [i for i, l in enumerate(lines) if M['components'].search(l)
                  and (M['original'].search(l) or M['evaluator'].search(l))]
        if not starts:
            continue
        preamble = strip_block(lines[:starts[0]])
        for k, s in enumerate(starts):
            e = starts[k + 1] if k + 1 < len(starts) else len(lines)
            rec = parse_sheet(lines[s:e])
            rec.update({'volume': volume, 'page': pno, 'index_on_page': k,
                        'preamble': preamble if k == 0 else ''})
            out.append(rec)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('volume')
    ap.add_argument('--out')
    ap.add_argument('--stats', action='store_true')
    a = ap.parse_args()
    recs = segment(a.volume)
    out = pathlib.Path(a.out) if a.out else volume_root(a.volume) / 'boxes' / f'{a.volume}.jsonl'
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w') as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    kinds = collections.Counter(r['kind'] for r in recs)
    print(f'{a.volume}: {len(recs)} sheets on {len({r["page"] for r in recs})} pages, {dict(kinds)}, '
          f'{sum(r["continued"] for r in recs)} continuations -> {out}')
    if a.stats:
        boxes = collections.Counter(b for r in recs for b, t in r['boxes'].items() if t)
        flags = collections.Counter(f for r in recs for f in r['flags'])
        print('boxes filled:', dict(boxes))
        print('flags:', dict(flags))


main()
