<script lang="ts">
	import { resolve } from '$app/paths';
	import AgencyScatter from '#lib/components/AgencyScatter.svelte';
	import { formatDecimal, formatInteger, formatPercentage } from '#lib/format.js';
	import { filterRows, sortRows, type SortDirection, type SortKey } from '#lib/rows.js';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	let query = $state('');
	let sortKey = $state<SortKey | null>(null);
	let sortDirection = $state<SortDirection>('desc');

	const columns: { key: SortKey; label: string }[] = [
		{ key: 'name', label: 'Agency' },
		{ key: 'words', label: 'Words' },
		{ key: 'density', label: 'Restrictions / 1k' },
		{ key: 'stale_share', label: 'Unchanged since 2017' },
		{ key: 'flagged_parts', label: 'Flagged parts' }
	];

	const topLevelCount = $derived(data.agencies.filter((agency) => agency.parent_slug === null).length);
	const filteredRows = $derived(filterRows(data.agencies, query));
	const rows = $derived(sortKey ? sortRows(filteredRows, sortKey, sortDirection) : filteredRows);

	function sortBy(key: SortKey) {
		if (sortKey === key) {
			sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
		} else {
			sortKey = key;
			sortDirection = key === 'name' ? 'asc' : 'desc';
		}
	}
</script>

<svelte:head>
	<title>Agencies · eCFR Analyzer</title>
	<meta
		name="description"
		content="Compare federal agencies by regulatory word count, restriction density, and recorded changes."
	/>
</svelte:head>

<div class="page-intro">
	<div>
		<p class="eyebrow">Agency explorer</p>
		<h1>Agencies, in perspective.</h1>
	</div>
	<p class="intro-copy">Explore the size and language of the federal rulebook. Compare agencies, then open a profile to see their recorded changes.</p>
</div>

<section class="chart-section" aria-labelledby="scatter-title">
	<div class="section-heading">
		<p class="eyebrow">01 / The landscape</p>
		<h2 id="scatter-title">Size and restriction density</h2>
		<p>Each point is a top-level agency with at least 1,000 words. The word-count axis uses a logarithmic scale.</p>
		<p class="chart-hint">Select a point to explore an agency.</p>
	</div>
	<div class="chart-frame">
		<AgencyScatter agencies={data.agencies} />
	</div>
</section>

<section class="directory" aria-labelledby="directory-title">
	<div class="directory-toolbar">
		<div>
			<p class="eyebrow">02 / The directory</p>
			<h2 id="directory-title">Browse agencies</h2>
			<p class="result-count" aria-live="polite" aria-atomic="true">
				{#if query.trim()}
					{rows.length} {rows.length === 1 ? 'match' : 'matches'} across {data.agencies.length} agencies
				{:else}
					{topLevelCount} top-level agencies
				{/if}
			</p>
		</div>
		<div class="search-field">
			<label for="agency-search">Find an agency</label>
			<input
				id="agency-search"
				data-testid="search"
				type="search"
				bind:value={query}
				placeholder="Search names or abbreviations…"
				aria-describedby="search-help"
			/>
			<p id="search-help">Search includes sub-agencies. Select a column heading to sort.</p>
		</div>
	</div>

	<div class="table-scroll" role="region" aria-label="Agency comparison">
		<table data-testid="agencies">
			<caption class="sr-only">Federal agency regulatory metrics. Select an agency to view its profile.</caption>
			<thead>
				<tr>
					{#each columns as column (column.key)}
						<th
							scope="col"
							data-sort={column.key}
							aria-sort={sortKey === column.key
								? (sortDirection === 'asc' ? 'ascending' : 'descending')
								: undefined}
						>
							<button type="button" onclick={() => sortBy(column.key)}>
								<span>{column.label}</span>
								<span class="sort-indicator" aria-hidden="true">
									{sortKey === column.key ? (sortDirection === 'asc' ? '▲' : '▼') : '↕'}
								</span>
							</button>
						</th>
					{/each}
				</tr>
			</thead>
			<tbody>
				{#each rows as agency (agency.slug)}
					<tr data-slug={agency.slug}>
						<td>
							<a
								class="agency-link"
								href={`${resolve('/agency/[slug]', { slug: agency.slug })}/`}
							>
								<span>{agency.name}</span>
								{#if agency.short_name}
									<span class="agency-abbreviation">{agency.short_name}</span>
								{/if}
							</a>
							{#if agency.parent_slug}
								<span class="subagency-label">Sub-agency</span>
							{/if}
						</td>
						<td class="numeric">{formatInteger(agency.words)}</td>
						<td class="numeric">{formatDecimal(agency.density)}</td>
						<td class="numeric">{formatPercentage(agency.stale_share)}</td>
						<td class="numeric">{formatInteger(agency.flagged_parts)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
	{#if rows.length === 0}
		<div class="empty-state">
			<h3>No agencies match “{query.trim()}”.</h3>
			<p>Try a shorter name or an abbreviation.</p>
			<button class="text-button" type="button" onclick={() => (query = '')}>Clear search</button>
		</div>
	{/if}
	<p class="data-note">Unchanged is the share of current sections with no recorded change since January 1, 2017. Flagged parts are candidates for review based on text metrics.</p>
</section>
