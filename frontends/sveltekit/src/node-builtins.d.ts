// The offline scaffold does not include @types/node, and dependencies are fixed.
// Declare only the built-in API signatures used by the build and fixture tests.
declare module 'node:fs' {
	export function readFileSync(path: string | URL, encoding: 'utf8'): string;
}

declare module 'node:fs/promises' {
	export function readFile(path: string | URL, encoding: 'utf8'): Promise<string>;
}

declare module 'node:path' {
	export function resolve(...paths: string[]): string;
}

declare module 'node:process' {
	export function cwd(): string;
	export const env: Record<string, string | undefined>;
}
