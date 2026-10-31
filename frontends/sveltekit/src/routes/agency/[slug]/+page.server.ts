import { error } from '@sveltejs/kit';
import { getAgencies, getAgencyDetail, getAgencyHistory } from '#lib/server/fixtures.js';
import type { EntryGenerator, PageServerLoad } from './$types';

export const entries: EntryGenerator = async () => {
	const agencies = await getAgencies();
	return agencies.map(({ slug }) => ({ slug }));
};

export const load: PageServerLoad = async ({ params }) => {
	const agencies = await getAgencies();
	const row = agencies.find((agency) => agency.slug === params.slug);
	if (!row) error(404, 'Agency not found');

	const [agency, years] = await Promise.all([
		getAgencyDetail(row.slug),
		getAgencyHistory(row.slug)
	]);
	const parent = agencies.find((agency) => agency.slug === row.parent_slug) ?? null;
	return { agency, years, parent };
};
