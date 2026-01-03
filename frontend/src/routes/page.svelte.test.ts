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

vi.mock('$lib/auth', () => ({
	isAuthenticated: {
		subscribe: vi.fn((callback) => {
			callback(false);
			return () => {};
		})
	}
}));

describe('/+page.svelte', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	test('should render loading text', () => {
		render(Page);
		expect(screen.getByText('Loading...')).toBeInTheDocument();
	});
});
