import { writable, derived } from 'svelte/store';
import { browser } from '$app/environment';
import { goto } from '$app/navigation';

// User interface
export interface User {
	id: number;
	username: string;
	email: string | null;
}

// Collaborator interface (includes permission level)
export interface Collaborator {
	id: number;
	username: string;
	email: string | null;
	permission: 'read' | 'write';
}

// Create a writable store with an initial value from localStorage if in browser
const initialToken = browser ? window.localStorage.getItem('access_token') : null;
export const token = writable<string | null>(initialToken);

// Refresh token store
const initialRefreshToken = browser ? window.localStorage.getItem('refresh_token') : null;
export const refreshToken = writable<string | null>(initialRefreshToken);

// Update localStorage whenever the token changes
if (browser) {
	token.subscribe((value) => {
		if (value) {
			window.localStorage.setItem('access_token', value);
		} else {
			window.localStorage.removeItem('access_token');
		}
	});
	refreshToken.subscribe((value) => {
		if (value) {
			window.localStorage.setItem('refresh_token', value);
		} else {
			window.localStorage.removeItem('refresh_token');
		}
	});
}

// Derived store to check if the user is authenticated
export const isAuthenticated = derived(token, ($token) => $token !== null);

// User store
export const user = writable<User | null>(null);

// Function to log the user out
export function logout() {
	token.set(null);
	refreshToken.set(null);
	user.set(null);
}

const API_BASE_URL = 'http://localhost:8000/api';

// 防止多個請求同時觸發 refresh
let refreshPromise: Promise<boolean> | null = null;

/**
 * 使用 refresh token 換取新的 access token
 * 回傳 true 表示刷新成功，false 表示失敗（需要重新登入）
 */
export async function refreshAccessToken(): Promise<boolean> {
	// 如果已經有一個 refresh 正在進行，等待它完成
	if (refreshPromise) return refreshPromise;

	refreshPromise = (async () => {
		const storedRefreshToken = browser ? window.localStorage.getItem('refresh_token') : null;
		if (!storedRefreshToken) return false;

		try {
			const response = await fetch(`${API_BASE_URL}/token/refresh`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ refresh: storedRefreshToken })
			});

			if (!response.ok) return false;

			const data = await response.json();
			token.set(data.access);
			return true;
		} catch {
			return false;
		}
	})().finally(() => {
		refreshPromise = null;
	});

	return refreshPromise;
}

async function apiFetch(url: string, options: RequestInit = {}, _isRetry = false) {
	const authToken = browser ? window.localStorage.getItem('access_token') : null;
	const headers = new Headers(options.headers || {});
	if (authToken) {
		headers.set('Authorization', `Bearer ${authToken}`);
	}
	if (!headers.has('Content-Type')) {
		headers.append('Content-Type', 'application/json');
	}

	const response = await fetch(`${API_BASE_URL}${url}`, {
		...options,
		headers
	});

	if (!response.ok) {
		if (response.status === 401 && !_isRetry) {
			// 嘗試用 refresh token 換取新的 access token，成功則重試一次
			const refreshed = await refreshAccessToken();
			if (refreshed) {
				return apiFetch(url, options, true);
			}

			// Refresh 也失敗，登出
			logout();
			if (browser) {
				goto('/login');
			}
			throw new Error('Unauthorized');
		}

		// 嘗試從 response body 提取錯誤訊息
		let errorMessage = `API request failed: ${response.statusText}`;
		try {
			const errorData = await response.json();
			const detail = errorData.detail;
			if (typeof detail === 'string') {
				errorMessage = detail;
			} else if (Array.isArray(detail) && detail.length > 0 && typeof detail[0]?.msg === 'string') {
				// Django Ninja 驗證錯誤格式: [{type, loc, msg, ctx}]
				errorMessage = detail
					.filter((e: { msg?: unknown }) => typeof e?.msg === 'string')
					.map((e: { msg: string }) => e.msg)
					.join('; ');
			} else if (typeof errorData.message === 'string') {
				errorMessage = errorData.message;
			}
		} catch {
			// 無法解析 JSON，使用預設訊息
		}

		throw new Error(errorMessage);
	}

	if (response.status === 204) {
		return null;
	}

	return response.json();
}

export function get(url: string) {
	return apiFetch(url, { method: 'GET' });
}

export function post(url: string, data: Record<string, unknown>, signal?: AbortSignal) {
	return apiFetch(url, {
		method: 'POST',
		body: JSON.stringify(data),
		signal
	});
}

export function put(url: string, data: Record<string, unknown>) {
	return apiFetch(url, {
		method: 'PUT',
		body: JSON.stringify(data)
	});
}

export function del(url: string) {
	return apiFetch(url, { method: 'DELETE' });
}

// Fetch current user info
export async function fetchCurrentUser(): Promise<User | null> {
	if (!browser) return null;

	const currentToken = window.localStorage.getItem('access_token');
	if (!currentToken) {
		user.set(null);
		return null;
	}

	try {
		const userData = await get('/auth/me');
		user.set(userData);
		return userData;
	} catch {
		user.set(null);
		return null;
	}
}
