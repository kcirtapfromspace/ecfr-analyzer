/** The fields used by the agency directory and scatter plot. */
export interface AgencyRow {
	slug: string;
	name: string;
	short_name: string | null;
	parent_slug: string | null;
	words: number | null;
	density: number | null;
	stale_share: number | null;
	flagged_parts: number | null;
}

export interface HistoryYear {
	year: number;
	substantive: number;
	nonsubstantive: number;
	removed: number;
}
