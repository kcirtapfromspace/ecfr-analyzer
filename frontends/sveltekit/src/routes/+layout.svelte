<script lang="ts">
	import favicon from '#lib/assets/atlas.svg';
	import { resolve } from '$app/paths';
	import type { LayoutProps } from './$types';
	import '../app.css';

	let { children }: LayoutProps = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<a class="skip-link" href="#main">Skip to content</a>
<header class="site-header">
	<a class="brand" href={resolve('/')} aria-label="eCFR Analyzer home">
		<span class="brand-mark">eCFR</span>
		<span>Regulatory atlas</span>
	</a>
	<span class="site-caption">Electronic Code of Federal Regulations</span>
</header>

<main id="main">
	{@render children()}
</main>

<footer class="site-footer">
	<span>eCFR Analyzer · Agency explorer</span>
	<span>Metrics describe regulatory text and recorded changes.</span>
</footer>
