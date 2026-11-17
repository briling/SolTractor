"""Example cases of the NIST row pairing (provenance.pair_rows) and of continuation pages (to_nomad.pair_sheets).

Run: uv run --with pytest --with hypothesis pytest tests

A row is reduced to its conditions (temperature in K, pressure in Pa or None); a table is
a list of rows; a sheet a list of tables. Expected results are written out per case.
"""
import importlib.util, pathlib

import pytest

from provenance import pair_rows
from sdstable import column


def T(*temps):
    """A table of rows given by temperature only."""
    return [(t, None) for t in temps]


P, C = 'position', 'conditions'

CASES = [
    # (ours, gold, expected): per table, per row, (partner, reason)
    pytest.param([T(298.15, 303.15, 308.15, 313.15, 318.15)], [T(298.15, 303.15, 308.15, 313.15, 318.15)],
                 [[((0, 0), C), ((0, 1), C), ((0, 2), C), ((0, 3), C), ((0, 4), C)]],
                 id='same_shape_in_order'),
    pytest.param([T(298.15, 303.15, 380.15, 313.15, 318.15)], [T(298.15, 303.15, 308.15, 313.15, 318.15)],
                 [[((0, 0), C), ((0, 1), C), ((0, 2), P), ((0, 3), C), ((0, 4), C)]],
                 id='misread_t_keeps_its_slot'),
    pytest.param([T(250, 252)], [T(251, 252)],
                 [[((0, 0), P), ((0, 1), C)]],
                 id='misread_t_in_two_row_table'),
    pytest.param([T(300, 310, 320)], [T(320, 310, 300)],
                 [[((0, 2), C), ((0, 1), C), ((0, 0), C)]],
                 id='reversed_table'),
    pytest.param([T(250, 251, 252, 253, 254)], [T(251, 250, 252, 253, 254)],
                 [[((0, 1), C), ((0, 0), C), ((0, 2), C), ((0, 3), C), ((0, 4), C)]],
                 id='two_rows_swapped'),
    pytest.param([T(298.15)], [T(293.15)],
                 [[((0, 0), P)]],
                 id='single_row_temperatures_differ'),
    pytest.param([T(300, 310, 330, 340)], [T(300, 310, 320, 330, 340)],
                 [[((0, 0), C), ((0, 1), C), ((0, 3), C), ((0, 4), C)]],
                 id='fewer_rows_distinct_t'),
    pytest.param([T(298.15, 298.15, 298.15, 310)], [T(298.15, 298.15, 298.15, 310, 320)],
                 [[((0, 0), C), ((0, 1), C), ((0, 2), C), ((0, 3), C)]],
                 id='equal_t_series_same_count'),
    pytest.param([T(313.15, 313.15, 313.15)], [T(284.65, 284.65, 313.15, 313.15, 313.15)],
                 [[((0, 2), C), ((0, 3), C), ((0, 4), C)]],
                 id='equal_t_series_after_rows_only_gold_has'),
    pytest.param([T(298.15, 298.15, 298.15)], [T(298.15, 298.15, 298.15, 298.15)],
                 [[(None, 'ambiguous'), (None, 'ambiguous'), (None, 'ambiguous')]],
                 id='equal_t_series_differing_count'),
    pytest.param([T(300, 300, 310)], [T(300, 310, 320)],
                 [[(None, 'ambiguous'), (None, 'ambiguous'), ((0, 1), C)]],
                 id='duplicated_row_is_ambiguous'),
    pytest.param([T(None, 300, 310)], [T(300, 310, 320)],
                 [[(None, 'no_conditions'), ((0, 0), C), ((0, 1), C)]],
                 id='missing_t_no_free_slot'),
    pytest.param([T(None, 310, 320)], [T(300, 310, 320)],
                 [[((0, 0), P), ((0, 1), C), ((0, 2), C)]],
                 id='missing_t_free_slot'),
    pytest.param([T(300, 310)], [],
                 [[(None, 'no_gold_tables'), (None, 'no_gold_tables')]],
                 id='no_gold_tables'),
    pytest.param([T(300, 310)], [[]],
                 [[(None, 'no_gold_tables'), (None, 'no_gold_tables')]],
                 id='gold_table_without_rows'),
    pytest.param([T(300, 310), T(320, 330, 340)], [T(300, 310), T(320, 330, 340)],
                 [[((0, 0), C), ((0, 1), C)], [((1, 0), C), ((1, 1), C), ((1, 2), C)]],
                 id='two_tables_same_shape'),
    pytest.param([T(300, 310), T(320, 330)], [T(300, 310, 320, 330)],
                 [[((0, 0), C), ((0, 1), C)], [((0, 2), C), ((0, 3), C)]],
                 id='table_split_at_page_break'),
    pytest.param([[(300, 101325.0)]], [[(300, None), (310, None)]],
                 [[((0, 0), C)]],
                 id='pressure_one_side'),
    pytest.param([[(300, 101325.0), (310, None)]], [[(300, 200000.0), (310, None)]],
                 [[((0, 0), P), ((0, 1), C)]],
                 id='pressure_disagrees_keeps_slot'),
    pytest.param([T(300, 305, 310)], [T(300, 310)],
                 [[((0, 0), C), (None, 'no_partner'), ((0, 1), C)]],
                 id='inserted_row_no_partner'),
    pytest.param([T(300, 305)], [T(300, 310, 320)],
                 [[((0, 0), C), (None, 'ambiguous')]],
                 id='unagreeing_row_several_free_slots'),
    pytest.param([T(298.3, 310)], [T(298.0, 298.4, 310)],
                 [[((0, 1), C), ((0, 2), C)]],
                 id='graded_agreement_picks_closer'),
]


@pytest.mark.parametrize('ours, gold, expected', CASES)
def test_pair_rows(ours, gold, expected):
    assert [[(hit, why) for hit, why, _ in t] for t in pair_rows(ours, gold)] == expected


@pytest.mark.parametrize('ours, gold, expected', [
    pytest.param([T(298.3, 310)], [T(298.0, 298.4, 310)], [[0.444444, 1.0]], id='graded_choice_has_margin'),
    pytest.param([T(298.15, 298.15)], [T(298.15, 298.15)], [[0.0, 0.0]], id='accepted_tie_has_zero_margin'),
    pytest.param([T(250, 252)], [T(251, 252)], [[None, 1.0]], id='slot_pair_has_no_margin'),
])
def test_margins(ours, gold, expected):
    """How much the disagreement rises without each pair: recorded in the trace as the pair's confidence."""
    assert [[m for _, _, m in t] for t in pair_rows(ours, gold)] == expected


def load_to_nomad():
    path = pathlib.Path(__file__).resolve().parent.parent / 'scripts' / 'to_nomad.py'
    spec = importlib.util.spec_from_file_location('to_nomad', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def table(*rows):
    """Prepared rows of one record: (header, columns, cells, note, sub-table) with a T/K column."""
    cols = [column('T/K')]
    return [(['T/K'], cols, [str(t)], '', bi) for bi, t in rows]


PARENT = {'volume': 'SDS-60', 'page': 41, 'index_on_page': 0, 'sheet_id': 'SDS-60/p041/0'}
CONT = {'volume': 'SDS-60', 'page': 42, 'index_on_page': 0, 'sheet_id': 'SDS-60/p042/0', 'continues': 'SDS-60/p041/0'}
GOLD = {'60_1': [T(300, 310, 320, 330, 340)]}


@pytest.mark.parametrize('cont_rows, expected', [
    pytest.param([(0, 330), (0, 340)],
                 {('SDS-60/p042/0', 0): ('SDS-60/p041/0/t0/r3', '60_1/t0/r3', 'conditions'),
                  ('SDS-60/p042/0', 1): ('SDS-60/p041/0/t0/r4', '60_1/t0/r4', 'conditions')},
                 id='continuation_extends_last_table'),
    pytest.param([(0, 330), (1, 340)],
                 {('SDS-60/p042/0', 0): ('SDS-60/p041/0/t0/r3', '60_1/t0/r3', 'conditions'),
                  ('SDS-60/p042/0', 1): ('SDS-60/p041/0/t1/r0', '60_1/t0/r4', 'conditions')},
                 id='continuation_second_table_opens_t1'),
])
def test_continuation_joins_its_sheet(cont_rows, expected):
    tn = load_to_nomad()
    prepared = [(PARENT, [], None, None, table((0, 300), (0, 310), (0, 320))),
                (CONT, [], None, None, table(*cont_rows))]
    out = tn.pair_sheets(prepared, {'SDS-60/p041/0': '60_1'}, GOLD, None)
    assert {k: v for k, v in out.items() if k[0] == 'SDS-60/p042/0'} == expected
