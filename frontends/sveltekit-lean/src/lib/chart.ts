// A Svelte action that draws a Chart.js chart on a canvas and redraws it when its config changes.
import {
	BarController,
	BarElement,
	CategoryScale,
	Chart,
	Legend,
	LinearScale,
	LogarithmicScale,
	PointElement,
	ScatterController,
	Tooltip,
	type ChartConfiguration
} from 'chart.js';

Chart.register(BarController, BarElement, CategoryScale, Legend, LinearScale, LogarithmicScale, PointElement, ScatterController, Tooltip);

export function chart(canvas: HTMLCanvasElement, config: ChartConfiguration) {
	let instance = new Chart(canvas, config);
	return {
		update(next: ChartConfiguration) {
			instance.destroy();
			instance = new Chart(canvas, next);
		},
		destroy: () => instance.destroy()
	};
}
