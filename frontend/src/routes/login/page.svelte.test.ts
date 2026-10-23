import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/toast', () => ({ toastError: vi.fn(), toastSuccess: vi.fn() }));
vi.mock('$lib/auth', () => ({
	token: { set: vi.fn() },
	refreshToken: { set: vi.fn() },
	fetchCurrentUser: vi.fn(),
	publicPost: vi.fn()
}));

import Page from './+page.svelte';
import { token, refreshToken, fetchCurrentUser, publicPost } from '$lib/auth';
import { goto } from '$app/navigation';
import { toastError } from '$lib/toast';

async function submit(username: string, password: string) {
	await fireEvent.input(screen.getByLabelText('Username'), { target: { value: username } });
	await fireEvent.input(screen.getByLabelText('Password'), { target: { value: password } });
	await fireEvent.click(screen.getByRole('button', { name: /Sign In/ }));
}

describe('Login page', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('stores both tokens, loads the user and goes to the dashboard', async () => {
		vi.mocked(publicPost).mockResolvedValue({
			ok: true,
			json: async () => ({ access: 'access-1', refresh: 'refresh-1' })
		} as Response);
		render(Page);

		await submit('alice', 's3cret');

		await waitFor(() => expect(goto).toHaveBeenCalledWith('/dashboard'));
		expect(publicPost).toHaveBeenCalledWith('/token/pair', {
			username: 'alice',
			password: 's3cret'
		});
		expect(token.set).toHaveBeenCalledWith('access-1');
		expect(refreshToken.set).toHaveBeenCalledWith('refresh-1');
		expect(fetchCurrentUser).toHaveBeenCalled();
		expect(toastError).not.toHaveBeenCalled();
	});

	it('shows an error and stays on the page when credentials are rejected', async () => {
		vi.mocked(publicPost).mockResolvedValue({ ok: false } as Response);
		render(Page);

		await submit('alice', 'wrong');

		await waitFor(() =>
			expect(toastError).toHaveBeenCalledWith('Login failed. Please check your credentials.')
		);
		expect(token.set).not.toHaveBeenCalled();
		expect(goto).not.toHaveBeenCalled();
		expect(screen.getByRole('button', { name: /Sign In/ })).toBeEnabled();
	});

	it('disables the button while signing in', async () => {
		vi.mocked(publicPost).mockImplementation(() => new Promise(() => {}));
		render(Page);

		await submit('alice', 's3cret');

		expect(await screen.findByRole('button', { name: /Signing in/ })).toBeDisabled();
	});
});
