import { getAgencies } from '#lib/server/fixtures.js';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => ({ agencies: await getAgencies() });
