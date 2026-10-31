<script lang="ts">
	import type { ChartConfiguration } from 'chart.js';
	import { chart } from '#lib/chart.js';
	import { formatDecimal, formatInt } from '#lib/table.js';

	let { data } = $props();
	const series = [
		['substantive', 'Substantive'],
		['nonsubstantive', 'Non-substantive'],
		['removed', 'Removed']
	] as const;
	const history: ChartConfiguration = $derived({
		type: 'bar',
		data: {
			labels: data.years.map((y) => y.year),
			datasets: series.map(([key, label]) => ({ label, data: data.years.map((y) => y[key]) }))
		},
		options: { maintainAspectRatio: false, scales: { x: { stacked: true }, y: { stacked: true } } }
	});
</script>

<h2 data-testid="detail-name">{data.name}</h2>
<dl>
	<dt>Words</dt>
	<dd data-testid="detail-words">{formatInt(data.words)}</dd>
	<dt>Restrictions / 1k</dt>
	<dd data-testid="detail-density">{formatDecimal(data.density)}</dd>
</dl>
<div class="chart"><canvas data-testid="history" use:chart={history}></canvas></div>
