// Pure table logic: no DOM, unit-tested with Vitest.
export type Agency = {
	slug: string;
	name: string;
	short_name: string | null;
	parent_slug: string | null;
	words: number;
	density: number | null;
	stale_share: number | null;
	flagged_parts: number;
};
export type SortKey = 'name' | 'words' | 'density' | 'stale_share' | 'flagged_parts';
export type Direction = 'ascending' | 'descending';

/** Text columns start ascending, number columns descending. */
export const firstDirection = (key: SortKey): Direction => (key === 'name' ? 'ascending' : 'descending');

/** Sort agencies by one column; nulls rank lowest. */
export function sortRows(rows: Agency[], key: SortKey, dir: Direction): Agency[] {
	const value = (a: Agency) => (key === 'name' ? a.name.toLowerCase() : (a[key] ?? -Infinity));
	const sign = dir === 'ascending' ? 1 : -1;
	return [...rows].sort((a, b) => {
		const x = value(a);
		const y = value(b);
		return sign * (x < y ? -1 : x > y ? 1 : 0);
	});
}

/** Agencies matching a search across name and abbreviation; an empty query shows top-level agencies only. */
export function filterRows(rows: Agency[], query: string): Agency[] {
	const q = query.trim().toLowerCase();
	if (!q) return rows.filter((a) => !a.parent_slug);
	return rows.filter((a) => `${a.name} ${a.short_name ?? ''}`.toLowerCase().includes(q));
}

export const formatInt = (n: number | null) => (n == null ? '—' : n.toLocaleString('en-US'));
export const formatDecimal = (x: number | null) => (x == null ? '—' : x.toFixed(1));
export const formatPercent = (x: number | null) => (x == null ? '—' : `${(100 * x).toFixed(1)}%`);
