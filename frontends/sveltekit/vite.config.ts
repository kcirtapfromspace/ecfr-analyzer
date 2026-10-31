import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import { env } from 'node:process';

const basePath = env.BASE_PATH ?? '';

if (basePath !== '' && (!basePath.startsWith('/') || basePath.endsWith('/'))) {
	throw new Error('BASE_PATH must be empty or start with / and have no trailing slash.');
}

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},

			adapter: adapter(),
			paths: { base: basePath as '' | `/${string}` }
		}),
		{
			name: 'name-chart-chunk',
			enforce: 'post',
			configEnvironment(name, config) {
				if (name !== 'client') return;
				const output = config.build?.rolldownOptions?.output;
				if (!output || Array.isArray(output)) return;
				const originalName = output.chunkFileNames;
				return {
					build: {
						rolldownOptions: {
							output: {
								// Preserve Kit's naming (especially its manifest) for every other chunk.
								chunkFileNames(chunk) {
									if (chunk.name === 'chart') return '_app/immutable/chunks/chart.[hash].js';
									return typeof originalName === 'function'
										? originalName(chunk)
										: (originalName ?? '_app/immutable/chunks/[hash].js');
								}
							}
						}
					}
				};
			}
		}
	],
	build: {
		rolldownOptions: {
			output: {
				codeSplitting: {
					groups: [{ name: 'chart', test: /node_modules[\\/]chart\.js[\\/]/ }]
				}
			}
		}
	}
});
