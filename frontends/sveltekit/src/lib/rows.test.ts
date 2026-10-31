import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { filterRows, sortRows } from '#lib/rows.js';
import type { AgencyRow } from '#lib/types.js';

const agencies: AgencyRow[] = JSON.parse(
	readFileSync(new URL('../../../fixtures/api/agencies.json', import.meta.url), 'utf8')
);

function agency(overrides: Partial<AgencyRow>): AgencyRow {
	return {
		slug: 'example',
		name: 'Example agency',
		short_name: null,
		parent_slug: null,
		words: 1_000,
		density: 5,
		stale_share: 0.5,
		flagged_parts: 1,
		...overrides
	};
}

describe('sortRows', () => {
	it('puts the highest-density agency first when descending', () => {
		const sorted = sortRows(filterRows(agencies, ''), 'density', 'desc');

		expect(sorted[0].name).toBe(
			'Architectural and Transportation Barriers Compliance Board'
		);
	});

	it('puts null density values after all known values when descending', () => {
		const sorted = sortRows(agencies, 'density', 'desc');
		const firstNull = sorted.findIndex((row) => row.density === null);

		expect(firstNull).toBeGreaterThan(0);
		expect(sorted.slice(firstNull).every((row) => row.density === null)).toBe(true);
	});

	it('puts the first alphabetical agency first when ascending', () => {
		const sorted = sortRows(filterRows(agencies, ''), 'name', 'asc');

		expect(sorted[0].name).toBe('Administrative Committee of the Federal Register');
	});

	it('compares agency names without case sensitivity and preserves equal names', () => {
		const rows = [
			agency({ slug: 'b', name: 'bravo' }),
			agency({ slug: 'a1', name: 'ALPHA' }),
			agency({ slug: 'a2', name: 'alpha' })
		];

		expect(sortRows(rows, 'name', 'asc').map((row) => row.slug)).toEqual(['a1', 'a2', 'b']);
		expect(sortRows(rows, 'name', 'desc').map((row) => row.slug)).toEqual(['b', 'a1', 'a2']);
	});

	it.each(['words', 'density', 'stale_share', 'flagged_parts'] as const)(
		'sorts %s numerically in both directions with nulls last',
		(key) => {
			const rows = [
				agency({ slug: 'missing', [key]: null }),
				agency({ slug: 'ten', [key]: 10 }),
				agency({ slug: 'two', [key]: 2 }),
				agency({ slug: 'zero', [key]: 0 })
			];

			expect(sortRows(rows, key, 'asc').map((row) => row.slug)).toEqual([
				'zero', 'two', 'ten', 'missing'
			]);
			expect(sortRows(rows, key, 'desc').map((row) => row.slug)).toEqual([
				'ten', 'two', 'zero', 'missing'
			]);
		}
	);

	it('does not mutate the input array or its rows', () => {
		const rows = Object.freeze([
			Object.freeze(agency({ slug: 'two', words: 2 })),
			Object.freeze(agency({ slug: 'one', words: 1 }))
		]);

		expect(sortRows(rows, 'words', 'asc').map((row) => row.slug)).toEqual(['one', 'two']);
		expect(rows.map((row) => row.slug)).toEqual(['two', 'one']);
	});
});

describe('filterRows', () => {
	it('matches exactly two occupational agencies, including one sub-agency', () => {
		const matched = filterRows(agencies, 'occupational');

		expect(matched).toHaveLength(2);
		expect(matched.filter((row) => row.parent_slug !== null)).toHaveLength(1);
	});

	it('returns the 153 top-level agencies for an empty query', () => {
		const matched = filterRows(agencies, '');

		expect(matched).toHaveLength(153);
		expect(matched.every((row) => row.parent_slug === null)).toBe(true);
	});

	it('matches short names and mixed-case queries with surrounding whitespace', () => {
		expect(filterRows(agencies, '  ePa ').map((row) => row.slug)).toContain(
			'environmental-protection-agency'
		);
		expect(filterRows(agencies, '  OCCUPATIONAL  ')).toEqual(
			filterRows(agencies, 'occupational')
		);
	});

	it('treats whitespace-only queries as empty and returns a new array', () => {
		const matched = filterRows(agencies, ' \t\n ');

		expect(matched).toEqual(filterRows(agencies, ''));
		expect(matched).not.toBe(agencies);
	});

	it('returns no results when there is no substring match, including null short names', () => {
		expect(filterRows([agency({ short_name: null })], 'no such agency')).toEqual([]);
	});
});
