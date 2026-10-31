<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import {
		Chart,
		ScatterController,
		PointElement,
		LinearScale,
		LogarithmicScale,
		Tooltip
	} from 'chart.js';
	import type { AgencyRow } from '#lib/types.js';

	Chart.register(ScatterController, PointElement, LinearScale, LogarithmicScale, Tooltip);

	let { agencies }: { agencies: AgencyRow[] } = $props();
	let canvas = $state<HTMLCanvasElement>();

	const integer = new Intl.NumberFormat('en-US');
	const decimal = new Intl.NumberFormat('en-US', {
		minimumFractionDigits: 1,
		maximumFractionDigits: 1
	});

	interface AgencyPoint {
		x: number;
		y: number;
		name: string;
		slug: string;
	}

	// Effects run only in the browser and clean up before a prop change or navigation.
	$effect(() => {
		if (!canvas) return;
		const chartCanvas = canvas;
		const points: AgencyPoint[] = agencies
			.filter(
				(agency): agency is AgencyRow & { words: number; density: number } =>
					agency.parent_slug === null &&
					agency.words !== null &&
					agency.words >= 1_000 &&
					agency.density !== null
			)
			.map((agency) => ({
				x: agency.words,
				y: agency.density,
				name: agency.name,
				slug: agency.slug
			}));

		const chart = new Chart<'scatter', AgencyPoint[]>(chartCanvas, {
			type: 'scatter',
			data: {
				datasets: [
					{
						label: 'Top-level agencies',
						data: points,
						backgroundColor: '#226456a6',
						borderColor: '#226456',
						borderWidth: 1,
						pointRadius: 4,
						pointHoverRadius: 6,
						pointHitRadius: 5
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
						type: 'logarithmic',
						min: 1_000,
						title: { display: true, text: 'Words · logarithmic scale', color: '#58645d' },
						grid: { color: '#e8ece7' },
						ticks: {
							color: '#58645d',
							maxTicksLimit: 6,
							callback: (value) => integer.format(Number(value))
						}
					},
					y: {
						type: 'linear',
						beginAtZero: true,
						title: { display: true, text: 'Restrictions / 1k words', color: '#58645d' },
						grid: { color: '#e8ece7' },
						ticks: {
							color: '#58645d',
							maxTicksLimit: 6,
							callback: (value) => decimal.format(Number(value))
						}
					}
				},
				plugins: {
					legend: { display: false },
					tooltip: {
						callbacks: {
							title: (items) => (items[0]?.raw as AgencyPoint | undefined)?.name ?? '',
							label: (item) => {
								const point = item.raw as AgencyPoint;
								return `${integer.format(point.x)} words · ${decimal.format(point.y)} restrictions / 1k`;
							}
						}
					}
				},
				onHover: (_event, elements) => {
					chartCanvas.style.cursor = elements.length ? 'pointer' : 'default';
				},
				onClick: (_event, elements) => {
					const element = elements[0];
					if (element) {
						void goto(`${resolve('/agency/[slug]', { slug: points[element.index].slug })}/`);
					}
				}
			}
		});

		return () => chart.destroy();
	});
</script>

<div class="chart" data-testid="scatter">
	<canvas
		bind:this={canvas}
		aria-label="Top-level agencies with at least 1,000 words, comparing word count on a logarithmic scale with restrictions per 1,000 words. The agency table contains the same values."
	>
		Compare agency words and restrictions in the table below.
	</canvas>
</div>

<style>
	.chart {
		position: relative;
		width: 100%;
		height: 340px;
		min-width: 0;
	}
</style>
