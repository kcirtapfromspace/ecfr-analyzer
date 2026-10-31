import agencies from '../../../fixtures/api/agencies.json';
import type { Agency } from '#lib/table.js';

// Runs at build time; only the fields the page uses are serialized into the prerendered HTML.
export const load = () => ({
	agencies: agencies.map(
		({ slug, name, short_name, parent_slug, words, density, stale_share, flagged_parts }): Agency => ({
			slug, name, short_name, parent_slug, words, density, stale_share, flagged_parts
		})
	)
});
