"""Ids, page regions and the decision trace shared by the converters and the exporter.

Every unit of the conceptual hierarchy has a stable id built from where it was first
printed: a sheet is `SDS-60/p041/0` (volume, first page, position on that page) and keeps
that id on every page it covers; its logical tables are `.../t0`, `.../t1` (the
sub-tables `sdstable.split_blocks` separates, continuation pages included); a row is
`.../t0/r3`, counted within its table.

A region is a rectangle on one page as one witness read it. Its `level` says how fine it
is (`block` for a MinerU block, usually most of a page; `band` for a crop band), so a row
that only has its band says so rather than pretending to a row-level location.

The trace is append-only jsonl: one record per decision (which sheet a crop belongs to,
which NIST row a row of ours corresponds to), each with the run id, the candidates, the
choice and the reason. A re-run appends under a new run id, so two runs can be compared.
"""
import datetime, json, pathlib, subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent

T_FULL, T_ZERO = 0.05, 0.5      # K: temperatures agree fully within T_FULL, not at all beyond T_ZERO
P_REL = 0.005                   # pressures printed on both sides must agree within this fraction
UNMATCHED = 1.0                 # cost of leaving a row unpaired; a pair costs 1 - agreement < 1
POSITION = 1e-6                 # cost per squared row distance between the two positions: a tie-breaker only
TIE = 1e-9
BLOCKED = 1e9


def sheet_id(volume: str, page: int, index_on_page: int) -> str:
    """Id of a data sheet: the volume, the page it starts on and its position there."""
    return f'{volume}/p{page:03d}/{index_on_page}'


def sheet_id_of(record: dict) -> str:
    """Id of a boxes record: its own `sheet_id`, else the one its position implies (records written before ids existed)."""
    return record.get('sheet_id') or sheet_id(record['volume'], record['page'], record['index_on_page'])


def table_id(sheet: str, table: int) -> str:
    return f'{sheet}/t{table}'


def row_id(sheet: str, table: int, row: int) -> str:
    return f'{sheet}/t{table}/r{row}'


def region(witness: str, page: int, level: str, source: str, bbox: list[float] | None = None,
           y0: float | None = None, y1: float | None = None) -> dict:
    """A rectangle on a page as one witness read it.

    `bbox` is normalised [x0, y0, x1, y1] (MinerU); a crop band has only its vertical
    extent `y0`/`y1` in PDF points, as the crop manifest records it."""
    out = {'witness': witness, 'page': page, 'level': level, 'source': source}
    if bbox is not None:
        out['bbox'] = bbox
    if y0 is not None:
        out.update(y0=y0, y1=y1, units='pt')
    return out


def run_id() -> str:
    """UTC time of the run and the commit it ran from."""
    try:
        rev = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        rev = 'nogit'
    return f"{datetime.datetime.now(datetime.timezone.utc):%Y%m%dT%H%M%SZ}-{rev}"


class Trace:
    """Append-only decision log of one run."""

    def __init__(self, path: pathlib.Path):
        self.path, self.run = path, run_id()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = self.path.open('a')

    def decide(self, decision: str, subject: str, choice, reason: str, candidates: list | None = None, **extra) -> None:
        rec = {'run': self.run, 'decision': decision, 'subject': subject, 'choice': choice, 'reason': reason}
        if candidates is not None:
            rec['candidates'] = candidates
        rec.update(extra)
        self._f.write(json.dumps(rec, ensure_ascii=False) + '\n')

    def close(self) -> None:
        self._f.close()


def agreement(ours: tuple, gold: tuple) -> float | None:
    """Graded agreement of two rows' conditions, from 0 to 1, or None when either has no temperature.

    The temperature agreement is 1 within T_FULL and falls linearly to 0 at T_ZERO, so a
    value rounded on one side (25 °C against a printed 298.2 K) still agrees. Pressures
    count only where both rows give one, and then must agree within P_REL; a pressure on
    one side only does not count against the pair."""
    (t, p), (gt, gp) = ours, gold
    if t is None or gt is None:
        return None
    if p is not None and gp is not None and abs(p - gp) > P_REL * max(abs(gp), 1e-12):
        return 0.0
    d = abs(t - gt)
    return 1.0 if d <= T_FULL else max(0.0, (T_ZERO - d) / (T_ZERO - T_FULL))


def pair_rows(ours: list[list[tuple]], gold: list[list[tuple]]) -> list[list[tuple]]:
    """Restore the mapping between the rows of one sheet and the ground-truth rows, without looking at the scored values.

    `ours` and `gold` are the logical tables of the sheet, each a list of rows, each row
    its conditions `(temperature in K or None, pressure in Pa or None)`. Rows are matched
    across the whole sheet; the split into tables is not used, so a table cut at a page
    break on one side pairs with the uncut table on the other.

    Step 1, rows with a partner in conditions. A row of ours *agrees* with a ground-truth
    row when `agreement` is above 0. Every row that agrees with at least one ground-truth
    row takes part in a one-to-one assignment that minimises the summed disagreement
    (1 - agreement per pair, UNMATCHED per row left out), with the squared distance
    between the two rows' positions as a small tie-breaker. The square matters: among
    rows that tie on conditions it is smallest only for the assignment that keeps their
    order, also when one side holds other rows before them (a summed absolute distance
    is then the same for every order). The assignment is solved exactly, per
    group of rows connected by agreement. For each pair the assignment is solved again
    without it: if the disagreement does not rise, the conditions alone did not choose
    this partner (a series printed at one temperature). Such a tie is accepted, in order,
    only when the group holds as many rows of ours as of the ground truth; otherwise
    every row of the group stays unpaired as `ambiguous`.

    Step 2, rows without a partner in conditions: a misread or missing temperature. Such
    a row lies between the nearest rows above and below it that step 1 paired (its
    anchors). It takes the unclaimed ground-truth rows between the anchors' partners when
    there are as many of those as there are such rows of ours between the anchors, in
    order (`position`). This places a misread row in its own slot even after a row was
    lost earlier in the table, so the misread is scored as a mismatch instead of being
    dropped.

    Returns:
        Per table of `ours`, per row, a triple `(partner, reason, margin)`. A pair has
        `partner` `(t, r)` and reason `conditions` (step 1; `margin` is how much the
        disagreement rises without this pair, 0.0 for an accepted tie) or `position`
        (step 2; `margin` None). An unpaired row has `partner` None, `margin` None and
        reason `no_gold_tables` (the ground truth has no row for this sheet),
        `ambiguous` (several rows share these conditions in different numbers on the two
        sides, or a slot between anchors cannot be told apart), `no_conditions` (no
        temperature, and no free slot between its anchors) or `no_partner` (it agrees with
        no ground-truth row and no slot is free between its anchors).
    """
    flat = [(ti, ri, c) for ti, t in enumerate(ours) for ri, c in enumerate(t)]
    gflat = [(ti, ri, c) for ti, t in enumerate(gold) for ri, c in enumerate(t)]
    result = {}
    if not gflat:
        return [[(None, 'no_gold_tables', None)] * len(t) for t in ours]
    agree = {(i, j): a for i, (_, _, c) in enumerate(flat) for j, (_, _, g) in enumerate(gflat)
             if (a := agreement(c, g))}
    # step 1: groups of rows connected by agreement, each solved as an assignment
    for rows, cols in _groups(agree):
        pairs, margins, ties = _solve_group(rows, cols, agree)
        balanced = len(rows) == len(cols)
        for i in rows:
            j = pairs.get(i)
            if j is None:
                result[i] = (None, 'ambiguous' if ties else 'no_partner', None)
            elif ties and not balanced:
                result[i] = (None, 'ambiguous', None)
            else:
                result[i] = (j, 'conditions', margins[i])
    # step 2: rows without agreement, placed between their anchors
    claimed = {r[0] for r in result.values() if r[0] is not None}
    anchors = sorted((i, r[0]) for i, r in result.items() if r[0] is not None)
    loose = [i for i in range(len(flat)) if i not in result]
    for run in _runs(loose):
        above = [j for i, j in anchors if i < run[0]]
        below = [j for i, j in anchors if i > run[-1]]
        lo = above[-1] if above else -1                    # partner of the nearest anchor above
        hi = below[0] if below else len(gflat)
        if lo > hi:                                        # the ground truth lists this stretch in reverse
            lo, hi = hi, lo
        slots = [j for j in range(lo + 1, hi) if j not in claimed]
        if len(slots) == len(run):
            for i, j in zip(run, slots):
                result[i] = (j, 'position', None)
                claimed.add(j)
        else:
            for i in run:
                why = 'ambiguous' if len(slots) > len(run) else 'no_conditions' if flat[i][2][0] is None else 'no_partner'
                result[i] = (None, why, None)
    out = [[None] * len(t) for t in ours]
    for i, (ti, ri, _) in enumerate(flat):
        j, why, margin = result[i]
        out[ti][ri] = ((gflat[j][0], gflat[j][1]) if j is not None else None, why, margin)
    return out


def _runs(idx: list[int]) -> list[list[int]]:
    """Consecutive indices grouped into runs: [1, 2, 5] -> [[1, 2], [5]]."""
    runs = []
    for i in idx:
        if runs and runs[-1][-1] == i - 1:
            runs[-1].append(i)
        else:
            runs.append([i])
    return runs


def _groups(agree: dict) -> list[tuple[list[int], list[int]]]:
    """Connected groups of the bipartite agreement graph: (our rows, ground-truth rows)."""
    parent = {}
    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for i, j in agree:
        parent[find(('o', i))] = find(('g', j))
    groups = {}
    for i, j in agree:
        g = groups.setdefault(find(('o', i)), (set(), set()))
        g[0].add(i); g[1].add(j)
    return [(sorted(a), sorted(b)) for a, b in groups.values()]


def _solve_group(rows: list[int], cols: list[int], agree: dict) -> tuple[dict[int, int], dict[int, float], bool]:
    """Best assignment of one group (our row -> ground-truth row), the margin of each pair, and whether any pair was a tie."""
    def solve(blocked=None):
        cost = [[(1 - agree[i, j]) + POSITION * (i - j) ** 2 if (i, j) in agree and (i, j) != blocked else BLOCKED
                 for j in cols] + [UNMATCHED] * len(rows) for i in rows]
        match = _assign(cost)
        pairs = {rows[a]: cols[b] for a, b in match.items() if b < len(cols) and cost[a][b] < BLOCKED}
        disagreement = sum(1 - agree[i, j] for i, j in pairs.items()) + UNMATCHED * (len(rows) - len(pairs))
        return pairs, disagreement
    best, base = solve()
    margins = {}
    for i, j in best.items():
        _, without = solve((i, j))
        margins[i] = round(without - base, 6)
    return best, margins, any(m <= TIE for m in margins.values())


def _assign(cost: list[list[float]]) -> dict[int, int]:
    """Minimum-cost assignment of every row to a distinct column (rows <= columns): Hungarian method."""
    n, m = len(cost), len(cost[0])
    u, v, p, way = [0.0] * (n + 1), [0.0] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minv, used = [float('inf')] * (m + 1), [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], float('inf'), 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    return {p[j] - 1: j - 1 for j in range(1, m + 1) if p[j]}
