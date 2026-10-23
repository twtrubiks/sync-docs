import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@zerodevx/svelte-toast', () => ({
	toast: { push: vi.fn() }
}));

import { toast } from '@zerodevx/svelte-toast';
import { toastSuccess, toastError, toastWarning } from '$lib/toast';

describe('toast helpers', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it.each([
		['success', toastSuccess, '#22c55e', '#16a34a'],
		['error', toastError, '#ef4444', '#dc2626'],
		['warning', toastWarning, '#f59e0b', '#d97706']
	])('%s uses its colour theme', (_name, show, background, bar) => {
		show('訊息');

		expect(toast.push).toHaveBeenCalledWith('訊息', {
			theme: {
				'--toastBackground': background,
				'--toastColor': 'white',
				'--toastBarBackground': bar
			}
		});
	});
});
