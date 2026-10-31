import type { AgencyRow } from '#lib/types.js';

export type SortKey = 'name' | 'words' | 'density' | 'stale_share' | 'flagged_parts';
export type SortDirection = 'asc' | 'desc';

/** Sort a copy, keeping missing values last in either direction and preserving ties. */
export function sortRows<T extends AgencyRow>(
	rows: readonly T[],
	key: SortKey,
	direction: SortDirection
): T[] {
	const multiplier = direction === 'asc' ? 1 : -1;

	return [...rows].sort((a, b) => {
		const left = a[key];
		const right = b[key];

		if (left === null) return right === null ? 0 : 1;
		if (right === null) return -1;

		const comparison =
			typeof left === 'string' && typeof right === 'string'
				? left.toLowerCase().localeCompare(right.toLowerCase(), 'en-US')
				: Number(left) - Number(right);

		return comparison * multiplier;
	});
}

/** Search all agencies; a blank query restores the top-level directory. */
export function filterRows<T extends AgencyRow>(rows: readonly T[], query: string): T[] {
	const normalizedQuery = query.trim().toLowerCase();

	return rows.filter((row) =>
		normalizedQuery === ''
			? row.parent_slug === null
			: `${row.name} ${row.short_name ?? ''}`.toLowerCase().includes(normalizedQuery)
	);
}
