import agencies from '../../../../../fixtures/api/agencies.json';
import type { EntryGenerator, PageServerLoad } from './$types';

type Year = { year: number; substantive: number; nonsubstantive: number; removed: number };

// Build time only: every agency gets a prerendered page from its detail and history files.
const api = '../../../../../fixtures/api/agencies';
const details = import.meta.glob('../../../../../fixtures/api/agencies/*.json', { eager: true, import: 'default' });
const histories = import.meta.glob('../../../../../fixtures/api/agencies/*/history.json', { eager: true, import: 'default' });

export const entries: EntryGenerator = () => agencies.map(({ slug }) => ({ slug }));

export const load: PageServerLoad = ({ params }) => {
	const { name, words, density } = details[`${api}/${params.slug}.json`] as { name: string; words: number; density: number | null };
	const { years } = histories[`${api}/${params.slug}/history.json`] as { years: Year[] };
	return { name, words, density, years };
};
