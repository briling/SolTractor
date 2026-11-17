"""Properties of the NIST row pairing under realistic damage to our copy of a table.

A ground-truth table of distinct temperatures is generated; our copy is the same table
with one kind of damage a reader causes (a row dropped, read twice, inserted, its
temperature misread or lost, the table split at a page break) or with the ground truth
reordered. The generator knows which ground-truth row each of our rows came from, so
every pair can be checked against the truth instead of against a restatement of the rule.

Run: uv run --with pytest --with hypothesis pytest tests
"""
from dataclasses import dataclass

from hypothesis import given, settings, strategies as st

from provenance import pair_rows

DAMAGE = ('none', 'drop', 'duplicate', 'insert', 'misread', 'missing_t', 'split', 'reorder', 'swap')


@dataclass
class Case:
    damage: str
    ours: list[list[tuple]]          # our tables
    gold: list[list[tuple]]          # ground-truth tables (one)
    truth: list[list[int | None]]    # per our row, the ground-truth row it came from (None: not from any)
    damaged: set[tuple[int, int]]    # our rows the damage touched


@st.composite
def cases(draw) -> Case:
    # distinct temperatures 1 K apart or more, far beyond the 0.05 K tolerance
    temps = draw(st.lists(st.integers(250, 400), min_size=2, max_size=12, unique=True))
    gold = [(float(t), None) for t in temps]
    rows = list(zip(gold, range(len(gold))))              # (conditions, source row)
    damage = draw(st.sampled_from(DAMAGE))
    damaged, split_at = set(), None
    unused = st.integers(250, 400).filter(lambda t: t not in temps).map(float)
    i = draw(st.integers(0, len(rows) - 1))
    if damage == 'drop':
        del rows[i]
    elif damage == 'duplicate':
        rows.insert(i + 1, rows[i])
        damaged = {i, i + 1}
    elif damage == 'insert':
        rows.insert(i, ((draw(unused), None), None))
        damaged = {i}
    elif damage == 'misread':
        rows[i] = ((draw(unused), None), rows[i][1])
        damaged = {i}
    elif damage == 'missing_t':
        rows[i] = ((None, None), rows[i][1])
        damaged = {i}
    elif damage == 'split':
        split_at = draw(st.integers(1, len(rows) - 1))
    elif damage == 'reorder':
        perm = draw(st.permutations(range(len(gold))))
        gold = [gold[k] for k in perm]                    # ground truth stored in another order
        where = {src: pos for pos, src in enumerate(perm)}
        rows = [(c, where[s]) for c, s in rows]
    elif damage == 'swap' and len(gold) > 1:              # the ground truth swaps two neighbouring rows
        j = min(i, len(gold) - 2)
        perm = list(range(len(gold))); perm[j], perm[j + 1] = perm[j + 1], perm[j]
        gold = [gold[k] for k in perm]
        where = {src: pos for pos, src in enumerate(perm)}
        rows = [(c, where[s]) for c, s in rows]
    tables = [rows[:split_at], rows[split_at:]] if split_at else [rows]
    return Case(damage, [[c for c, _ in t] for t in tables], [gold], [[s for _, s in t] for t in tables],
                {(0, k) for k in damaged})


def flat_pairs(result):
    return [(ti, ri, hit, why) for ti, t in enumerate(result) for ri, (hit, why, _) in enumerate(t)]


SETTINGS = settings(max_examples=500, derandomize=True, deadline=None)


@SETTINGS
@given(cases())
def test_one_result_per_row(case):
    result = pair_rows(case.ours, case.gold)
    assert [len(t) for t in result] == [len(t) for t in case.ours]


@SETTINGS
@given(cases())
def test_no_ground_truth_row_claimed_twice(case):
    hits = [hit for _, _, hit, _ in flat_pairs(pair_rows(case.ours, case.gold)) if hit]
    assert len(hits) == len(set(hits))


@SETTINGS
@given(cases())
def test_every_pair_is_the_true_partner(case):
    """No pair is invented: a row that pairs, pairs with the row it came from (position or conditions alike)."""
    for ti, ri, hit, why in flat_pairs(pair_rows(case.ours, case.gold)):
        if hit is not None:
            assert hit == (0, case.truth[ti][ri]), (case.damage, ti, ri, hit, why)


@SETTINGS
@given(cases())
def test_undamaged_rows_are_paired(case):
    """The partial-match guarantee: every row the damage did not touch finds its partner."""
    result = pair_rows(case.ours, case.gold)
    for ti, ri, hit, why in flat_pairs(result):
        if (ti, ri) not in case.damaged:
            assert hit is not None, (case.damage, ti, ri, why)


@SETTINGS
@given(cases())
def test_unpaired_reason_fits_the_damage(case):
    allowed = {'insert': {'no_partner'}, 'duplicate': {'ambiguous'},
               'misread': {'no_partner', 'ambiguous'}, 'missing_t': {'no_conditions', 'ambiguous'}}
    for ti, ri, hit, why in flat_pairs(pair_rows(case.ours, case.gold)):
        if hit is None:
            assert why in allowed.get(case.damage, set()), (case.damage, ti, ri, why)


@given(st.lists(st.integers(250, 400), min_size=1, max_size=12, unique=True))
@settings(derandomize=True)
def test_identical_tables_pair_row_by_row(temps):
    table = [(float(t), None) for t in temps]
    assert [(hit, why) for hit, why, _ in pair_rows([table], [table])[0]] == [((0, r), 'conditions') for r in range(len(table))]


@SETTINGS
@given(cases())
def test_misread_in_unchanged_table_is_scored(case):
    """A misread temperature in a table of unchanged shape still pairs, so the error is scored rather than lost."""
    if case.damage != 'misread':
        return
    result = pair_rows(case.ours, case.gold)
    for ti, ri in case.damaged:
        assert result[ti][ri][0] is not None, (len(case.ours[0]), result)
