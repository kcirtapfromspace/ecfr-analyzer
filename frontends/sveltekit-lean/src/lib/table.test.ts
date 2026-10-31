import { describe, expect, test } from 'vitest';
import agencies from '../../../fixtures/api/agencies.json';
import { filterRows, sortRows, type Agency } from './table';

const all = agencies as Agency[];
const topLevel = filterRows(all, '');

describe('table logic', () => {
	test('density descending puts the Access Board first', () => {
		expect(sortRows(topLevel, 'density', 'descending')[0].name).toBe('Architectural and Transportation Barriers Compliance Board');
	});

	test('nulls go last when descending', () => {
		const rows = sortRows(all, 'density', 'descending');
		const firstNull = rows.findIndex((a) => a.density === null);
		expect(firstNull).toBeGreaterThan(0);
		expect(rows.slice(firstNull).every((a) => a.density === null)).toBe(true);
	});

	test('name ascending is case-insensitive', () => {
		expect(sortRows(topLevel, 'name', 'ascending')[0].name).toBe('Administrative Committee of the Federal Register');
	});

	test('search spans sub-agencies', () => {
		const hits = filterRows(all, 'Occupational');
		expect(hits).toHaveLength(2);
		expect(hits.some((a) => a.parent_slug)).toBe(true);
	});

	test('an empty query shows only top-level agencies', () => {
		expect(topLevel).toHaveLength(153);
	});
});
