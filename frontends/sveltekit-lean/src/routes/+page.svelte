<script lang="ts">
	import type { ChartConfiguration } from 'chart.js';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { chart } from '#lib/chart.js';
	import {
		filterRows,
		firstDirection,
		formatDecimal,
		formatInt,
		formatPercent,
		sortRows,
		type Direction,
		type SortKey
	} from '#lib/table.js';

	let { data } = $props();
	let query = $state('');
	let sortKey = $state<SortKey>('words');
	let direction = $state<Direction>('descending');
	const rows = $derived(sortRows(filterRows(data.agencies, query), sortKey, direction));

	const columns: [SortKey, string][] = [
		['name', 'Agency'],
		['words', 'Words'],
		['density', 'Restrictions / 1k'],
		['stale_share', 'Unchanged since 2017'],
		['flagged_parts', 'Flagged parts']
	];

	function sortBy(key: SortKey) {
		direction = key === sortKey ? (direction === 'ascending' ? 'descending' : 'ascending') : firstDirection(key);
		sortKey = key;
	}

	const href = (slug: string) => resolve('/agency/[slug]', { slug });
	const plotted = $derived(data.agencies.filter((a) => !a.parent_slug && a.words >= 1000));
	const scatter: ChartConfiguration = $derived({
		type: 'scatter',
		data: { datasets: [{ data: plotted.map((a) => ({ x: a.words, y: a.density ?? 0 })) }] },
		options: {
			maintainAspectRatio: false,
			onClick: (_, hits) => hits.length && goto(href(plotted[hits[0].index].slug)),
			plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => plotted[c.dataIndex].name } } },
			scales: {
				x: { type: 'logarithmic', title: { display: true, text: 'Words (log scale)' } },
				y: { title: { display: true, text: 'Restriction terms per 1,000 words' } }
			}
		}
	});
</script>

<h1>eCFR Analyzer</h1>
<div class="chart"><canvas data-testid="scatter" use:chart={scatter}></canvas></div>
<input type="search" data-testid="search" placeholder="Filter agencies (includes sub-agencies)" aria-label="Filter agencies" bind:value={query} />
<table data-testid="agencies">
	<thead>
		<tr>
			{#each columns as [key, label] (key)}
				<th data-sort={key} aria-sort={key === sortKey ? direction : 'none'}>
					<button type="button" onclick={() => sortBy(key)}>{label}</button>
				</th>
			{/each}
		</tr>
	</thead>
	<tbody>
		{#each rows as a (a.slug)}
			<tr data-slug={a.slug}>
				<td><a href={href(a.slug)}>{a.short_name ? `${a.name} (${a.short_name})` : a.name}</a></td>
				<td>{formatInt(a.words)}</td>
				<td>{formatDecimal(a.density)}</td>
				<td>{formatPercent(a.stale_share)}</td>
				<td>{formatInt(a.flagged_parts)}</td>
			</tr>
		{/each}
	</tbody>
</table>
