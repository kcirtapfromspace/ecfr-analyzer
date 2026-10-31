"""Hand-made comparator checks; no network, application code, or raw cache."""

from contextlib import redirect_stdout
from copy import deepcopy
import io
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle


def fixture(count=3):
    rows = [dict(rank=i, title=1, part=str(i), heading='Part ' + str(i),
                 words=1000, score=float(count + 1 - i), flagged=i <= math.ceil(.1 * count),
                 inputs=dict.fromkeys(oracle.INPUTS, 0.0), z=dict.fromkeys(oracle.INPUTS, 0.0))
            for i in range(1, count + 1)]
    metrics = dict(readability={'sentences': 0, 'fk_grade': None},
                   sentence_types=dict.fromkeys(oracle.TYPES, 0), flagged_parts=0)
    expected = dict(eligible=count, flagged=math.ceil(.1 * count), candidates=rows,
                    agencies={slug: deepcopy(metrics) for slug in ('alpha', 'beta', 'empty')})
    return expected


def payload(expected, selected=None, slug=None):
    return dict(agency=slug, eligible=expected['eligible'], flagged=expected['flagged'],
                candidates=deepcopy((expected['candidates'] if selected is None else selected)[:500]))


def compare(expected, actual, selected=None, context='global'):
    mismatches = oracle.Mismatches()
    oracle.compare_candidates(actual, expected,
                              expected['candidates'] if selected is None else selected,
                              context, mismatches)
    return mismatches.fields


class ComparisonChecks(unittest.TestCase):
    def test_exact_scalars_nulls_and_numeric_tolerance(self):
        mismatches = oracle.Mismatches()
        for expected, actual in [(1, 1), (None, None), ('x', 'x'), (1.0, 1),
                                 (1.0, 1 + 5e-10), (0.0, 5e-13)]:
            mismatches.compare(expected, actual, 'value', 'valid')
        self.assertFalse(mismatches.fields)
        cases = [(1, True), (1, 1.0), (None, 0), ('x', 'y'),
                 (1.0, None), (1.0, float('nan')), (1.0, float('inf')),
                 (1.0, True), (0.0, 2e-12), (1.0, 1 + 2e-9),
                 (1.0, 10 ** 1000)]
        for index, (expected, actual) in enumerate(cases):
            mismatches.compare(expected, actual, str(index), 'invalid')
        self.assertEqual(len(mismatches.fields), len(cases))
        mismatches.compare({'nullable': None}, {}, 'keys', 'missing')
        self.assertIn('keys.nullable', mismatches.fields)

    def test_metadata_is_required_and_global_under_filter(self):
        expected = fixture()
        selected = expected['candidates'][1:]
        actual = payload(expected, selected, 'alpha')
        self.assertFalse(compare(expected, actual, selected, 'alpha'))
        actual['eligible'] = len(selected)
        self.assertIn('candidates.eligible', compare(expected, actual, selected, 'alpha'))
        actual = payload(expected)
        del actual['agency']
        self.assertIn('candidates.agency', compare(expected, actual))
        for field in ('eligible', 'flagged'):
            actual = payload(expected)
            actual[field] = float(actual[field])
            self.assertIn('candidates.' + field, compare(expected, actual))

    def test_duplicate_missing_and_unknown_candidate_ids(self):
        expected = fixture()
        actual = payload(expected)
        actual['candidates'][1] = deepcopy(actual['candidates'][0])
        self.assertIn('candidates.membership', compare(expected, actual))
        actual = payload(expected)
        actual['candidates'].pop()
        self.assertIn('candidates.length', compare(expected, actual))
        actual = payload(expected)
        actual['candidates'][0]['part'] = 'unknown'
        self.assertIn('candidates.membership', compare(expected, actual))
        actual['candidates'][0]['title'] = True
        self.assertIn('candidates.identity', compare(expected, actual))

    def test_nontie_order_rank_and_duplicate_rank_rejected(self):
        expected = fixture()
        actual = payload(expected)
        actual['candidates'][1], actual['candidates'][2] = actual['candidates'][2], actual['candidates'][1]
        self.assertIn('candidates.order', compare(expected, actual))
        self.assertIn('candidates.rank_order', compare(expected, actual))
        actual = payload(expected)
        actual['candidates'][1]['rank'] = 3
        self.assertIn('candidates.rank', compare(expected, actual))

    def test_pairwise_close_score_swap_and_limit_boundary_allowed(self):
        expected = fixture()
        expected['candidates'][2]['score'] = 2.0 - 1e-10
        actual = payload(expected)
        actual['candidates'][1], actual['candidates'][2] = actual['candidates'][2], actual['candidates'][1]
        for index, row in enumerate(actual['candidates'], 1):
            row['rank'] = index
        self.assertFalse(compare(expected, actual))
        expected = fixture(501)
        expected['candidates'][500]['score'] = 2.0 - 1e-10
        actual = payload(expected)
        actual['candidates'][-1] = deepcopy(expected['candidates'][500])
        actual['candidates'][-1]['rank'] = 500
        self.assertFalse(compare(expected, actual))

    def test_base_route_coverage_and_null_responses(self):
        expected = fixture()
        memberships = {'alpha': {(1, '1'), (1, '2')}, 'beta': {(1, '3')}, 'empty': set()}
        routes = {
            '/api/agencies': [dict(slug=slug, **metrics) for slug, metrics in expected['agencies'].items()],
            '/api/candidates?limit=500': payload(expected),
            '/api/candidates?agency=alpha&limit=500': payload(expected, expected['candidates'][:2], 'alpha'),
            '/api/candidates?agency=beta&limit=500': payload(expected, expected['candidates'][2:], 'beta'),
        }
        with patch.object(oracle, 'fetch', side_effect=lambda base, route, errors: routes[route]) as fetch:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(oracle.compare_base('mock', expected, memberships), 0)
        self.assertEqual({call.args[1] for call in fetch.call_args_list}, set(routes))
        with patch.object(oracle, 'fetch', return_value=None):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(oracle.compare_base('mock', expected, memberships), len(routes))
        duplicate = deepcopy(routes['/api/agencies'])
        duplicate[1] = deepcopy(duplicate[0])
        routes['/api/agencies'] = duplicate
        with patch.object(oracle, 'fetch', side_effect=lambda base, route, errors: routes[route]):
            with redirect_stdout(io.StringIO()):
                self.assertGreater(oracle.compare_base('mock', expected, memberships), 0)

    def test_summary_caps_examples_at_three(self):
        mismatches = oracle.Mismatches()
        for index in range(5):
            mismatches.add('field', 'context ' + str(index), 1, 2)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(mismatches.summary(), 5)
        self.assertEqual(len(mismatches.fields['field']['examples']), 3)
        self.assertEqual(output.getvalue().count('expected'), 3)
        self.assertIn('field: 5', output.getvalue())


if __name__ == '__main__':
    unittest.main()
