import { describe, test, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/svelte';
import Page from './+page.svelte';

// Mock the $app modules
vi.mock('$app/navigation', () => ({
	goto: vi.fn()
}));

vi.mock('$app/environment', () => ({
	browser: true
}));

const authState = vi.hoisted(() => ({ value: false }));

vi.mock('$lib/auth', () => ({
	isAuthenticated: {
		subscribe: vi.fn((callback) => {
			callback(authState.value);
			return () => {};
		})
	}
}));

import { goto } from '$app/navigation';

describe('/+page.svelte', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	test('should render loading text', () => {
		render(Page);
		expect(screen.getByText('Loading...')).toBeInTheDocument();
	});

	test('redirects anonymous visitors to login without a history entry', () => {
		authState.value = false;
		render(Page);
		expect(goto).toHaveBeenCalledWith('/login', { replaceState: true });
	});

	test('redirects signed-in users to the dashboard', () => {
		authState.value = true;
		render(Page);
		expect(goto).toHaveBeenCalledWith('/dashboard', { replaceState: true });
		expect(goto).not.toHaveBeenCalledWith('/login', expect.anything());
	});
});
