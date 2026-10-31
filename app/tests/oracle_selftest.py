"""Hand-made Round 3 contract checks; run from root with Python -I."""

from contextlib import redirect_stderr
import gzip
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle


class OracleChecks(unittest.TestCase):
    def test_prose_skips_subtrees_but_keeps_tails(self):
        element = ET.fromstring(
            '<DIV5> Cafe\u0301 <P>Before<TABLE>hidden<MATH>also hidden</MATH>'
            'hidden tail</TABLE>after <I>italics</I> end.'
            '<MATH>hidden</MATH> Next.</P></DIV5>'
        )
        self.assertEqual(
            oracle.normalize(oracle.prose_nodes(element)),
            'Café Before after italics end. Next.',
        )
        self.assertEqual(oracle.normalize([' a\t b ', '\n c ']), 'a b c')

    def test_splitter_abbreviations_and_case(self):
        cases = [
            ('Dr. Smith. Next.', ['Dr. Smith.', 'Next.']),
            ('dr. Smith.', ['dr.', 'Smith.']),
            ('A. B. C. Next.', ['A. B. C. Next.']),
            ('Mr. ( ? Alice', ['Mr. ( ?', 'Alice']),
            ('See U.S.C. Section 3. Act.', ['See U.S.C. Section 3.', 'Act.']),
            ('Finished. lowercase stays.', ['Finished. lowercase stays.']),
            ('Done! (Next.) § 2? “Yes.”', ['Done!', '(Next.) § 2?', '“Yes.”']),
            ('!!! §', []),
            ('', []),
        ]
        for prose, expected in cases:
            with self.subTest(prose=prose):
                self.assertEqual(oracle.sentences(prose), expected)

    def test_classifier_precedence_and_word_boundaries(self):
        cases = {
            'Means you shall not submit.': 'definition',
            'You must not file.': 'prohibition',
            'No person may report.': 'prohibition',
            'You are required to file.': 'paperwork',
            'You must preserve records.': 'paperwork',
            'Required report.': 'obligation',
            'You must perform.': 'obligation',
            'It may be present.': 'permission',
            'A report exists.': 'other',
            'The remaynder reports something.': 'other',
        }
        for sentence, expected in cases.items():
            with self.subTest(sentence=sentence):
                self.assertEqual(oracle.classify(sentence), expected)

    def test_syllables_are_vowel_runs_without_dictionary_rules(self):
        for word, count in [('make', 2), ('queue', 1), ('rhythms', 1),
                            ('AEIOUY', 1), ('policy', 3), ('123', 1),
                            ('ÉTÉ', 1), ('中文', 1), ('cooperate', 4)]:
            with self.subTest(word=word):
                self.assertEqual(oracle.syllables(word), count)

    def test_measure_counts_and_first_match_classifier(self):
        element = ET.fromstring(
            '<DIV5><P>A means a report must be filed. You may not file. '
            'You must submit forms. You must act. You may rest. Quiet words.'
            '</P><TABLE>shall prohibited</TABLE><MATH>required</MATH></DIV5>'
        )
        counts = oracle.measure(element)
        self.assertEqual(counts['sentences'], 6)
        self.assertEqual(counts['sentence_types'], dict.fromkeys(
            ['definition', 'prohibition', 'paperwork', 'obligation',
             'permission', 'other'], 1))
        self.assertEqual(counts['restrictions'], 7)
        self.assertEqual(counts['passive_sentences'], 1)
        self.assertEqual(counts['words'] - counts['prose_words'], 3)

    def test_long_sentence_threshold_and_crossrefs(self):
        element = ET.fromstring('<P>' + ' '.join(['word'] * 40) + '. '
                                + ' '.join(['word'] * 41) + '.</P>')
        self.assertEqual(oracle.measure(element)['long_sentences'], 1)
        element = ET.fromstring(
            '<P>§ 1; paragraph (a); paragraphs (b); section 2; sections 3; '
            'part 4; parts 5; subpart a; subparts z; 5 U.S.C. 301.</P>')
        self.assertEqual(oracle.measure(element)['crossrefs'], 10)

    def test_readability_uses_counts_and_null_denominators(self):
        empty = dict.fromkeys(['prose_words', 'sentences', 'syllables',
                               'long_sentences', 'passive_sentences', 'crossrefs'], 0)
        result = oracle.readability(empty)
        self.assertEqual(result['sentences'], 0)
        self.assertTrue(all(v is None for k, v in result.items() if k != 'sentences'))
        result = oracle.readability(dict(prose_words=100, sentences=4,
                                         syllables=150, long_sentences=2,
                                         passive_sentences=1, crossrefs=3))
        self.assertEqual(result['words_per_sentence'], 25)
        self.assertAlmostEqual(result['fk_grade'], 11.86)
        self.assertEqual(result['long_share'], .5)
        self.assertEqual(result['passive_share'], .25)
        self.assertEqual(result['crossrefs_per_1k'], 30)

    def test_staleness_duplicate_or_latest_future_and_appendix(self):
        def row(part, ident, date, removed=False, kind='section'):
            return dict(part=part, identifier=ident, date=date, removed=removed,
                        substantive=False, type=kind)
        rows = [row('1', 'a', '2016-12-31'), row('1', 'b', '2017-01-01'),
                row('1', 'c', '2016-01-01', kind='appendix'),
                row('1', 'b', '2027-01-01', True),
                row('2', 'a', '2016-01-01'), row('2', 'a', '2016-01-01', True),
                row('3', 'a', '2016-01-01', True), row('3', 'a', '2020-01-01')]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'versions-1.json'
            path.write_text(json.dumps(dict(result_count=len(rows), content_versions=rows)))
            result = oracle.part_staleness(path, '2026-10-29')
        self.assertEqual(tuple(result['1']), (3, 2))
        self.assertEqual(tuple(result.get('2', (0, 0))), (0, 0))
        self.assertEqual(tuple(result['3']), (1, 0))

    def test_ranking_ties_population_and_eligibility(self):
        def part(title, number, ordinal, words=1000, count=10):
            return dict(title=title, part=number, ord=ordinal, heading='', words=words,
                        restrictions=0, prose_words=1000, sentences=count,
                        syllables=1000, part_stale_share=None,
                        sentence_types=dict.fromkeys(['definition', 'prohibition',
                            'paperwork', 'obligation', 'permission', 'other'], 0))
        parts = [part(10, '2', 0), part(2, '10', 1), part(2, '9', 0),
                 part(1, 'tiny', 0, words=999), part(1, 'empty', 1, count=0)]
        ranked = oracle.rank_parts(parts)
        self.assertEqual([(p['title'], p['part']) for p in ranked],
                         [(2, '9'), (2, '10'), (10, '2')])
        self.assertEqual([p['rank'] for p in ranked], [1, 2, 3])
        self.assertEqual([p['flagged'] for p in ranked], [True, False, False])
        self.assertTrue(all(abs(p['score']) < 1e-12 for p in ranked))
        two = [part(1, '1', 0, words=1000), part(1, '2', 1, words=10000)]
        ranked = oracle.rank_parts(two)
        self.assertAlmostEqual(ranked[0]['z']['size'], 1)
        self.assertAlmostEqual(ranked[1]['z']['size'], -1)
        self.assertTrue(all(math.isfinite(p['score']) for p in ranked))

    def test_raw_cache_integration_and_agency_set_rollups(self):
        first = 'You must send forms. ' * 250
        second = 'You may rest with them. ' * 200
        xml = (
            '<ECFR><DIV1 TYPE="TITLE" N="1"><DIV2 TYPE="SUBTITLE" N="A">'
            '<DIV3 TYPE="CHAPTER" N="I"><DIV4 TYPE="SUBCHAP" N="Outer">'
            '<DIV3 TYPE="CHAPTER" N="0"><DIV2 TYPE="SUBTITLE" N="B">'
            '<DIV4 TYPE="SUBCHAP" N="Inner">'
            '<DIV5 TYPE="PART" N="10"><HEAD>First</HEAD><P>' + first + '</P></DIV5>'
            '<DIV5 TYPE="PART" N="20"><HEAD>Next</HEAD><P>' + second + '</P></DIV5>'
            '</DIV4></DIV2></DIV3>'
            '<DIV5 TYPE="PART" N="30"><HEAD>Tiny</HEAD><P>You may rest.</P></DIV5>'
            '</DIV4></DIV3></DIV2></DIV1></ECFR>'
        )
        refs = [dict(title=1, subtitle='B', chapter='0', subchapter='Inner', part='10'),
                dict(title=1, part='10')]
        agencies = [
            dict(slug='parent', cfr_references=refs, children=[
                dict(slug='child', cfr_references=[dict(title=1, part='20')] * 2)]),
            dict(slug='small', cfr_references=[
                dict(title=1, subtitle='A', chapter='I', subchapter='Outer')], children=[]),
            dict(slug='reserved', cfr_references=[dict(title=35)], children=[]),
        ]
        def row(part, identifier, date, removed=False, kind='section'):
            return dict(part=part, identifier=identifier, date=date, removed=removed,
                        substantive=True, type=kind)
        rows = [row('10', 'a', '2016-01-01'), row('10', 'a', '2027-01-01', True),
                row('10', 'b', '2020-01-01', True, 'appendix'),
                row('20', 'a', '2020-01-01'), row('30', 'a', '2016-01-01'),
                row(None, 'orphan', '2016-01-01'), row('999', 'absent', '2016-01-01')]
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory)
            (raw / 'titles.json').write_text(json.dumps(dict(
                meta=dict(import_in_progress=False), titles=[
                    dict(number=1, reserved=False), dict(number=35, reserved=True)])))
            (raw / 'agencies.json').write_text(json.dumps(dict(agencies=agencies)))
            (raw / 'versions-1.json').write_text(json.dumps(dict(
                result_count=len(rows), content_versions=rows)))
            with gzip.open(raw / 'title-1.xml.gz', 'wt') as destination:
                destination.write(xml)
            with redirect_stderr(io.StringIO()):
                expected, memberships = oracle.build_expected(raw, '2026-10-29')
        self.assertEqual(expected['titles'], [1])
        self.assertEqual(len(expected['parts']), 3)
        one, two, tiny = expected['parts']
        self.assertEqual([(p['ord'], p['subtitle'], p['chapter'], p['subchapter'])
                          for p in expected['parts']],
                         [(0, 'B', '0', 'Inner'), (1, 'B', '0', 'Inner'),
                          (2, 'A', 'I', 'Outer')])
        self.assertEqual([(p['part_sections'], p['part_stale'])
                          for p in expected['parts']], [(1, 1), (1, 0), (1, 1)])
        self.assertEqual(memberships, {'parent': {(1, '10'), (1, '20')},
                                     'child': {(1, '20')}, 'small': {(1, '30')},
                                     'reserved': set()})
        self.assertEqual((expected['eligible'], expected['flagged']), (2, 1))
        self.assertEqual([p['part'] for p in expected['candidates']], ['10', '20'])
        self.assertAlmostEqual(expected['candidates'][0]['score'], .5)
        parent = expected['agencies']['parent']
        self.assertEqual(parent['readability']['sentences'], 450)
        self.assertEqual(parent['readability']['words_per_sentence'], 2002 / 450)
        self.assertAlmostEqual(parent['readability']['fk_grade'],
                               .39 * 2002 / 450 + 11.8 - 15.59)
        average = (one['readability']['words_per_sentence']
                   + two['readability']['words_per_sentence']) / 2
        self.assertNotAlmostEqual(parent['readability']['words_per_sentence'], average)
        types = dict.fromkeys(oracle.TYPES, 0)
        types.update(paperwork=250, permission=200)
        self.assertEqual(parent['sentence_types'], types)
        self.assertEqual({slug: data['flagged_parts']
                          for slug, data in expected['agencies'].items()},
                         {'parent': 1, 'child': 0, 'small': 0, 'reserved': 0})


if __name__ == '__main__':
    unittest.main()
