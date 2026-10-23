import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import { createRawSnippet } from 'svelte';

const state = vi.hoisted(() => ({ routeId: '/(protected)/dashboard' as string | null }));

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$app/stores', async () => {
	const { readable } = await import('svelte/store');
	return {
		page: {
			subscribe: (fn: (v: unknown) => void) =>
				readable({ route: { id: state.routeId } }).subscribe(fn)
		}
	};
});
vi.mock('$lib/auth', async () => {
	const { writable } = await import('svelte/store');
	return {
		isAuthenticated: writable(false),
		user: writable(null),
		logout: vi.fn(),
		fetchCurrentUser: vi.fn()
	};
});

import Layout from './+layout.svelte';
import { goto } from '$app/navigation';
import { isAuthenticated, user, logout, fetchCurrentUser } from '$lib/auth';
import type { Writable } from 'svelte/store';

const children = createRawSnippet(() => ({ render: () => '<p>page content</p>' }));

function setAuth(authenticated: boolean, currentUser: unknown = null) {
	(isAuthenticated as unknown as Writable<boolean>).set(authenticated);
	(user as unknown as Writable<unknown>).set(currentUser);
}

describe('root layout', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		state.routeId = '/(protected)/dashboard';
		setAuth(false);
	});

	it('redirects anonymous visitors away from protected routes', () => {
		render(Layout, { props: { children } });

		expect(goto).toHaveBeenCalledWith('/login');
	});

	it('lets anonymous visitors open public routes', () => {
		state.routeId = '/login';

		render(Layout, { props: { children } });

		expect(goto).not.toHaveBeenCalled();
		expect(screen.getByText('page content')).toBeInTheDocument();
		expect(screen.getByTitle('Login')).toHaveAttribute('href', '/login');
		expect(screen.getByTitle('Register')).toHaveAttribute('href', '/register');
		expect(screen.queryByTitle('Logout')).toBeNull();
	});

	it('loads the user for authenticated sessions that lack user data', () => {
		setAuth(true);

		render(Layout, { props: { children } });

		expect(goto).not.toHaveBeenCalled();
		expect(fetchCurrentUser).toHaveBeenCalledTimes(1);
	});

	it('greets a loaded user without refetching', () => {
		setAuth(true, { id: 1, username: 'alice', email: null });

		render(Layout, { props: { children } });

		expect(fetchCurrentUser).not.toHaveBeenCalled();
		expect(screen.getByText('歡迎, alice')).toBeInTheDocument();
		expect(screen.getByTitle('Dashboard')).toHaveAttribute('href', '/dashboard');
	});

	it('logs out and returns to the login page', async () => {
		setAuth(true, { id: 1, username: 'alice', email: null });
		render(Layout, { props: { children } });

		await fireEvent.click(screen.getByTitle('Logout'));

		expect(logout).toHaveBeenCalledTimes(1);
		expect(goto).toHaveBeenCalledWith('/login');
	});
});
