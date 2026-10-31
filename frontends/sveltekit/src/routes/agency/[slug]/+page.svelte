<script lang="ts">
	import { resolve } from '$app/paths';
	import AgencyHistory from '#lib/components/AgencyHistory.svelte';
	import { formatDecimal, formatInteger, formatPercentage } from '#lib/format.js';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<svelte:head>
	<title>{data.agency.name} · eCFR Analyzer</title>
	<meta
		name="description"
		content={`Regulatory word count, restriction density, and recorded change history for ${data.agency.name}.`}
	/>
</svelte:head>

<nav class="breadcrumbs" aria-label="Breadcrumb">
	<a href={resolve('/')}>All agencies</a>
	{#if data.parent}
		<span aria-hidden="true">/</span>
		<a href={`${resolve('/agency/[slug]', { slug: data.parent.slug })}/`}>{data.parent.name}</a>
	{/if}
</nav>

<div class="detail-intro">
	<p class="eyebrow">Agency profile{data.agency.short_name ? ` / ${data.agency.short_name}` : ''}</p>
	<h1 data-testid="detail-name">{data.agency.name}</h1>
	<p>
		Regulatory text across {formatInteger(data.agency.parts)} CFR parts.
		{#if data.agency.last_changed}
			Last recorded change: {data.agency.last_changed}.
		{:else}
			No recorded changes.
		{/if}
	</p>
</div>

<dl class="metrics">
	<div>
		<dt>Words</dt>
		<dd data-testid="detail-words">{formatInteger(data.agency.words)}</dd>
	</div>
	<div>
		<dt>Restrictions / 1k words</dt>
		<dd data-testid="detail-density">{formatDecimal(data.agency.density)}</dd>
	</div>
	<div>
		<dt>Unchanged since 2017</dt>
		<dd>{formatPercentage(data.agency.stale_share)}</dd>
	</div>
	<div>
		<dt>Flagged parts</dt>
		<dd>{formatInteger(data.agency.flagged_parts)}</dd>
	</div>
</dl>

<section class="chart-section history-section" aria-labelledby="history-title">
	<div class="section-heading">
		<p class="eyebrow">Recorded changes</p>
		<h2 id="history-title">An agency through time</h2>
		<p>Annual change records, grouped by substantive changes, nonsubstantive changes, and removals.</p>
		<p class="chart-hint">Years with no records are omitted.</p>
	</div>
	<div class="chart-frame">
		<AgencyHistory years={data.years} agencyName={data.agency.name} />
	</div>
</section>

{#if data.years.length > 0}
	<details class="history-data">
		<summary>View the history data</summary>
		<div class="table-scroll" role="region" aria-label="Annual change records">
			<table>
				<caption class="sr-only">Annual change records for {data.agency.name}</caption>
				<thead>
					<tr>
						<th scope="col">Year</th>
						<th scope="col">Substantive</th>
						<th scope="col">Nonsubstantive</th>
						<th scope="col">Removed</th>
					</tr>
				</thead>
				<tbody>
					{#each data.years as year (year.year)}
						<tr>
							<th scope="row">{year.year}</th>
							<td class="numeric">{formatInteger(year.substantive)}</td>
							<td class="numeric">{formatInteger(year.nonsubstantive)}</td>
							<td class="numeric">{formatInteger(year.removed)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</details>
{/if}

<p class="data-note">Unchanged sections have no recorded change since January 1, 2017. Flagged parts are candidates for review based on text metrics. These measures describe the text and its history.</p>
