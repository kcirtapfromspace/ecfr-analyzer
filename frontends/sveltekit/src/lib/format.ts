const integer = new Intl.NumberFormat('en-US');
const decimal = new Intl.NumberFormat('en-US', {
	minimumFractionDigits: 1,
	maximumFractionDigits: 1
});
const percentage = new Intl.NumberFormat('en-US', {
	style: 'percent',
	minimumFractionDigits: 1,
	maximumFractionDigits: 1
});

export function formatInteger(value: number | null): string {
	return value === null ? '—' : integer.format(value);
}

export function formatDecimal(value: number | null): string {
	return value === null ? '—' : decimal.format(value);
}

export function formatPercentage(value: number | null): string {
	return value === null ? '—' : percentage.format(value);
}
