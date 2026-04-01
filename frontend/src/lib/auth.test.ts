import { describe, it, expect, vi, beforeEach } from 'vitest';
import { get as storeGet } from 'svelte/store';

// ── Hoist: set up window.localStorage before auth.ts module loads ──
const { mockStorage, clearStorage, setStorage } = vi.hoisted(() => {
	const store: Record<string, string> = {};
	const storage = {
		getItem: vi.fn((key: string) => store[key] ?? null),
		setItem: vi.fn((key: string, value: string) => {
			store[key] = value;
		}),
		removeItem: vi.fn((key: string) => {
			delete store[key];
		})
	};
	(globalThis as Record<string, unknown>).window = { localStorage: storage };
	return {
		mockStorage: storage,
		clearStorage: () => {
			for (const k of Object.keys(store)) delete store[k];
		},
		setStorage: (key: string, value: string) => {
			store[key] = value;
		}
	};
});

const mockGoto = vi.hoisted(() => vi.fn());

vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$app/navigation', () => ({ goto: mockGoto }));

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

import {
	token,
	refreshToken,
	user,
	logout,
	refreshAccessToken,
	get as apiGet,
	post as apiPost,
	put as apiPut,
	del as apiDel,
	fetchCurrentUser
} from '$lib/auth';

// Helper: create a mock Response-like object
function createResponse(body: unknown, status = 200, statusText = 'OK') {
	return {
		ok: status >= 200 && status < 300,
		status,
		statusText,
		json: vi.fn().mockResolvedValue(body)
	};
}

// Helper: set up a logged-in state (stores + localStorage)
function setupAuth(accessToken = 'test-token', refresh = 'test-refresh') {
	setStorage('access_token', accessToken);
	setStorage('refresh_token', refresh);
	token.set(accessToken);
	refreshToken.set(refresh);
	vi.clearAllMocks();
}

describe('auth', () => {
	beforeEach(() => {
		token.set(null);
		refreshToken.set(null);
		user.set(null);
		clearStorage();
		mockFetch.mockReset();
		vi.clearAllMocks();
	});

	// ── API methods ──

	describe('get / post / put / del', () => {
		it('get() sends GET with Authorization header', async () => {
			setupAuth();
			mockFetch.mockResolvedValueOnce(createResponse({ id: 1 }));

			const result = await apiGet('/test');

			expect(result).toEqual({ id: 1 });
			expect(mockFetch).toHaveBeenCalledOnce();
			const [url, options] = mockFetch.mock.calls[0];
			expect(url).toBe('http://localhost:8000/api/test');
			expect(options.method).toBe('GET');
			expect(options.headers.get('Authorization')).toBe('Bearer test-token');
			expect(options.headers.get('Content-Type')).toBe('application/json');
		});

		it('post() sends POST with JSON body', async () => {
			setupAuth();
			mockFetch.mockResolvedValueOnce(createResponse({ success: true }));

			const result = await apiPost('/items', { name: 'test' });

			expect(result).toEqual({ success: true });
			const [url, options] = mockFetch.mock.calls[0];
			expect(url).toBe('http://localhost:8000/api/items');
			expect(options.method).toBe('POST');
			expect(options.body).toBe(JSON.stringify({ name: 'test' }));
		});

		it('put() sends PUT with JSON body', async () => {
			setupAuth();
			mockFetch.mockResolvedValueOnce(createResponse({ updated: true }));

			await apiPut('/items/1', { name: 'updated' });

			const [url, options] = mockFetch.mock.calls[0];
			expect(url).toBe('http://localhost:8000/api/items/1');
			expect(options.method).toBe('PUT');
			expect(options.body).toBe(JSON.stringify({ name: 'updated' }));
		});

		it('del() sends DELETE', async () => {
			setupAuth();
			mockFetch.mockResolvedValueOnce(createResponse(null, 204));

			await apiDel('/items/1');

			const [url, options] = mockFetch.mock.calls[0];
			expect(url).toBe('http://localhost:8000/api/items/1');
			expect(options.method).toBe('DELETE');
		});

		it('returns null for 204 response', async () => {
			setupAuth();
			mockFetch.mockResolvedValueOnce(createResponse(null, 204));

			const result = await apiDel('/items/1');
			expect(result).toBeNull();
		});

		it('throws error with detail string for non-401 errors', async () => {
			setupAuth();
			mockFetch.mockResolvedValueOnce(createResponse({ detail: 'Not found' }, 404, 'Not Found'));

			await expect(apiGet('/missing')).rejects.toThrow('Not found');
		});

		it('parses Django Ninja validation error format', async () => {
			setupAuth();
			mockFetch.mockResolvedValueOnce(
				createResponse(
					{
						detail: [
							{ type: 'value_error', loc: ['body'], msg: 'field required' },
							{ type: 'type_error', loc: ['body'], msg: 'invalid type' }
						]
					},
					422,
					'Unprocessable Entity'
				)
			);

			await expect(apiPost('/validate', {})).rejects.toThrow('field required; invalid type');
		});

		it('uses statusText when JSON parsing fails', async () => {
			setupAuth();
			mockFetch.mockResolvedValueOnce({
				ok: false,
				status: 500,
				statusText: 'Internal Server Error',
				json: vi.fn().mockRejectedValue(new Error('not json'))
			});

			await expect(apiGet('/error')).rejects.toThrow('API request failed: Internal Server Error');
		});
	});

	// ── 401 auto-retry ──

	describe('401 auto-retry', () => {
		it('retries request after successful token refresh', async () => {
			setupAuth('old-token', 'valid-refresh');

			mockFetch
				.mockResolvedValueOnce(createResponse(null, 401, 'Unauthorized'))
				.mockResolvedValueOnce(createResponse({ access: 'new-token' }))
				.mockResolvedValueOnce(createResponse({ id: 1 }));

			const result = await apiGet('/protected');

			expect(result).toEqual({ id: 1 });
			expect(mockFetch).toHaveBeenCalledTimes(3);

			// Verify refresh was called correctly
			const [refreshUrl, refreshOptions] = mockFetch.mock.calls[1];
			expect(refreshUrl).toBe('http://localhost:8000/api/token/refresh');
			expect(JSON.parse(refreshOptions.body)).toEqual({ refresh: 'valid-refresh' });

			// Verify retry used the new token
			const retryHeaders = mockFetch.mock.calls[2][1].headers;
			expect(retryHeaders.get('Authorization')).toBe('Bearer new-token');
		});

		it('logs out and redirects to /login when refresh fails', async () => {
			setupAuth('old-token', 'expired-refresh');

			mockFetch
				.mockResolvedValueOnce(createResponse(null, 401, 'Unauthorized'))
				.mockResolvedValueOnce(createResponse(null, 401, 'Unauthorized'));

			await expect(apiGet('/protected')).rejects.toThrow('Unauthorized');

			expect(storeGet(token)).toBeNull();
			expect(storeGet(refreshToken)).toBeNull();
			expect(mockGoto).toHaveBeenCalledWith('/login');
		});

		it('does not retry infinitely on persistent 401', async () => {
			setupAuth('old-token', 'valid-refresh');

			mockFetch
				.mockResolvedValueOnce(createResponse(null, 401, 'Unauthorized'))
				.mockResolvedValueOnce(createResponse({ access: 'new-token' }))
				.mockResolvedValueOnce(
					createResponse({ detail: 'Still unauthorized' }, 401, 'Unauthorized')
				);

			await expect(apiGet('/protected')).rejects.toThrow('Still unauthorized');
			// 3 calls total: original + refresh + retry. No 4th call.
			expect(mockFetch).toHaveBeenCalledTimes(3);
		});
	});

	// ── refreshAccessToken ──

	describe('refreshAccessToken', () => {
		it('refreshes token using refresh_token from localStorage', async () => {
			setStorage('refresh_token', 'my-refresh');
			vi.clearAllMocks();

			mockFetch.mockResolvedValueOnce(createResponse({ access: 'fresh-token' }));

			const success = await refreshAccessToken();

			expect(success).toBe(true);
			expect(storeGet(token)).toBe('fresh-token');
			expect(mockFetch).toHaveBeenCalledOnce();
		});

		it('returns false when refresh request fails', async () => {
			setStorage('refresh_token', 'bad-refresh');
			vi.clearAllMocks();

			mockFetch.mockResolvedValueOnce(createResponse(null, 401, 'Unauthorized'));

			const success = await refreshAccessToken();
			expect(success).toBe(false);
		});

		it('returns false when no refresh_token exists', async () => {
			const success = await refreshAccessToken();

			expect(success).toBe(false);
			expect(mockFetch).not.toHaveBeenCalled();
		});

		it('deduplicates concurrent refresh calls', async () => {
			setStorage('refresh_token', 'my-refresh');
			vi.clearAllMocks();

			mockFetch.mockResolvedValueOnce(createResponse({ access: 'fresh-token' }));

			const [r1, r2] = await Promise.all([refreshAccessToken(), refreshAccessToken()]);

			expect(r1).toBe(true);
			expect(r2).toBe(true);
			expect(mockFetch).toHaveBeenCalledOnce();
		});
	});

	// ── Stores and logout ──

	describe('stores and logout', () => {
		it('syncs token to localStorage on set', () => {
			token.set('new-access');
			expect(mockStorage.setItem).toHaveBeenCalledWith('access_token', 'new-access');
		});

		it('removes token from localStorage when set to null', () => {
			token.set('temp');
			vi.clearAllMocks();

			token.set(null);
			expect(mockStorage.removeItem).toHaveBeenCalledWith('access_token');
		});

		it('logout clears token, refreshToken, and user stores', () => {
			setupAuth();
			user.set({ id: 1, username: 'test', email: null });

			logout();

			expect(storeGet(token)).toBeNull();
			expect(storeGet(refreshToken)).toBeNull();
			expect(storeGet(user)).toBeNull();
		});
	});

	// ── fetchCurrentUser ──

	describe('fetchCurrentUser', () => {
		it('returns user data when token exists', async () => {
			setupAuth();
			const userData = { id: 1, username: 'alice', email: 'alice@example.com' };
			mockFetch.mockResolvedValueOnce(createResponse(userData));

			const result = await fetchCurrentUser();

			expect(result).toEqual(userData);
			expect(storeGet(user)).toEqual(userData);
		});

		it('returns null when no token in localStorage', async () => {
			const result = await fetchCurrentUser();

			expect(result).toBeNull();
			expect(mockFetch).not.toHaveBeenCalled();
		});
	});
});
