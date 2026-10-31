<script lang="ts">
	import {
		Chart,
		BarController,
		BarElement,
		CategoryScale,
		LinearScale,
		Tooltip,
		Legend
	} from 'chart.js';
	import type { HistoryYear } from '#lib/types.js';

	Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend);

	let { years, agencyName }: { years: HistoryYear[]; agencyName: string } = $props();
	let canvas = $state<HTMLCanvasElement>();
	const integer = new Intl.NumberFormat('en-US');

	$effect(() => {
		if (!canvas) return;

		const chart = new Chart(canvas, {
			type: 'bar',
			data: {
				labels: years.map((year) => String(year.year)),
				datasets: [
					{
						label: 'Substantive',
						data: years.map((year) => year.substantive),
						backgroundColor: '#226456'
					},
					{
						label: 'Nonsubstantive',
						data: years.map((year) => year.nonsubstantive),
						backgroundColor: '#9ba79f'
					},
					{
						label: 'Removed',
						data: years.map((year) => year.removed),
						backgroundColor: '#a76549'
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				animation: false,
				font: { family: "'Avenir Next', 'Segoe UI', sans-serif" },
				scales: {
					x: {
						stacked: true,
						grid: { display: false },
						ticks: { color: '#58645d' }
					},
					y: {
						stacked: true,
						beginAtZero: true,
						title: { display: true, text: 'Recorded changes', color: '#58645d' },
						grid: { color: '#e8ece7' },
						ticks: {
							color: '#58645d',
							precision: 0,
							maxTicksLimit: 6,
							callback: (value) => integer.format(Number(value))
						}
					}
				},
				plugins: {
					legend: {
						position: 'bottom',
						labels: { color: '#58645d', boxWidth: 12, boxHeight: 12, padding: 20 }
					},
					tooltip: {
						mode: 'index',
						intersect: false,
						callbacks: {
							label: (item) => `${item.dataset.label}: ${integer.format(item.parsed.y ?? 0)}`
						}
					}
				}
			}
		});

		return () => chart.destroy();
	});
</script>

<div class="chart" data-testid="history">
	<canvas
		bind:this={canvas}
		aria-label={`Annual recorded changes for ${agencyName}, stacked by substantive, nonsubstantive and removed. Expand View the history data below for the values.`}
	>
		Expand View the history data below for annual substantive, nonsubstantive and removed changes.
	</canvas>
	{#if years.length === 0}
		<p class="empty">No changes recorded since 2017.</p>
	{/if}
</div>

<style>
	.chart {
		position: relative;
		width: 100%;
		height: 340px;
		min-width: 0;
	}

	.empty {
		position: absolute;
		inset: 35% 0 auto;
		margin: 0;
		padding: 1rem;
		text-align: center;
		color: #58645d;
		background: #fafbf8;
	}

</style>
