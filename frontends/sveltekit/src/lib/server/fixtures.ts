import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { cwd } from 'node:process';
import type { AgencyRow, HistoryYear } from '#lib/types.js';

// This module is server-only. The static build serializes the page data it needs;
// the fixture directory is never copied into the site's public assets.
const fixtureDirectory = resolve(cwd(), '../fixtures/api');

export interface AgencyDetail extends AgencyRow {
	parts: number;
	last_changed: string | null;
}

async function readFixture<T>(path: string): Promise<T> {
	const contents = await readFile(resolve(fixtureDirectory, path), 'utf8');
	return JSON.parse(contents) as T;
}

function agencyRow(agency: AgencyRow): AgencyRow {
	return {
		slug: agency.slug,
		name: agency.name,
		short_name: agency.short_name,
		parent_slug: agency.parent_slug,
		words: agency.words,
		density: agency.density,
		stale_share: agency.stale_share,
		flagged_parts: agency.flagged_parts
	};
}

let agencies: Promise<AgencyRow[]> | undefined;

export function getAgencies(): Promise<AgencyRow[]> {
	return (agencies ??= readFixture<AgencyRow[]>('agencies.json').then((rows) => rows.map(agencyRow)));
}

export async function getAgencyDetail(slug: string): Promise<AgencyDetail> {
	const agency = await readFixture<AgencyDetail>(`agencies/${slug}.json`);
	return {
		...agencyRow(agency),
		parts: agency.parts,
		last_changed: agency.last_changed
	};
}

export async function getAgencyHistory(slug: string): Promise<HistoryYear[]> {
	const history = await readFixture<{ slug: string; years: HistoryYear[] }>(
		`agencies/${slug}/history.json`
	);
	return history.years;
}
