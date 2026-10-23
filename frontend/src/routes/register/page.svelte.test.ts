import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/toast', () => ({ toastError: vi.fn(), toastSuccess: vi.fn() }));
vi.mock('$lib/auth', () => ({ publicPost: vi.fn() }));

import Page from './+page.svelte';
import { publicPost } from '$lib/auth';
import { goto } from '$app/navigation';
import { toastError, toastSuccess } from '$lib/toast';

async function fill({
	username = 'alice',
	email = '',
	password = 'a-strong-pass',
	confirm = 'a-strong-pass'
} = {}) {
	await fireEvent.input(screen.getByLabelText('Username'), { target: { value: username } });
	await fireEvent.input(screen.getByPlaceholderText('your@email.com'), {
		target: { value: email }
	});
	await fireEvent.input(screen.getByPlaceholderText('Create a password'), {
		target: { value: password }
	});
	await fireEvent.input(screen.getByPlaceholderText('Confirm your password'), {
		target: { value: confirm }
	});
	await fireEvent.click(screen.getByRole('button', { name: /Create Account/ }));
}

describe('Register page', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('rejects mismatched passwords without calling the API', async () => {
		render(Page);

		await fill({ confirm: 'different' });

		expect(toastError).toHaveBeenCalledWith('Passwords do not match');
		expect(publicPost).not.toHaveBeenCalled();
	});

	it('registers without email when it is blank and redirects to login', async () => {
		vi.mocked(publicPost).mockResolvedValue({ ok: true } as Response);
		render(Page);

		await fill({ email: '   ' });

		await waitFor(() => expect(goto).toHaveBeenCalledWith('/login'));
		expect(publicPost).toHaveBeenCalledWith('/auth/register', {
			username: 'alice',
			password: 'a-strong-pass'
		});
		expect(toastSuccess).toHaveBeenCalledWith('Registration successful! Please log in.');
	});

	it('sends the trimmed email when provided', async () => {
		vi.mocked(publicPost).mockResolvedValue({ ok: true } as Response);
		render(Page);

		await fill({ email: '  alice@example.com ' });

		await waitFor(() => expect(publicPost).toHaveBeenCalled());
		expect(publicPost).toHaveBeenCalledWith('/auth/register', {
			username: 'alice',
			password: 'a-strong-pass',
			email: 'alice@example.com'
		});
	});

	it('shows the backend detail when registration fails', async () => {
		vi.mocked(publicPost).mockResolvedValue({
			ok: false,
			json: async () => ({ detail: '用戶名已存在' })
		} as Response);
		render(Page);

		await fill();

		await waitFor(() =>
			expect(toastError).toHaveBeenCalledWith('Registration failed: 用戶名已存在')
		);
		expect(goto).not.toHaveBeenCalled();
		expect(screen.getByRole('button', { name: /Create Account/ })).toBeEnabled();
	});

	it('falls back to the raw body or a generic message', async () => {
		vi.mocked(publicPost)
			.mockResolvedValueOnce({ ok: false, json: async () => ({ error: 'x' }) } as Response)
			.mockResolvedValueOnce({
				ok: false,
				json: async () => {
					throw new Error('not json');
				}
			} as unknown as Response);
		render(Page);

		await fill();
		await waitFor(() =>
			expect(toastError).toHaveBeenCalledWith('Registration failed: {"error":"x"}')
		);
		await fireEvent.click(screen.getByRole('button', { name: /Create Account/ }));
		await waitFor(() =>
			expect(toastError).toHaveBeenCalledWith('Registration failed: An unknown error occurred.')
		);
	});
});
