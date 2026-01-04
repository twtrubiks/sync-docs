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

// Update localStorage whenever the token changes
if (browser) {
	token.subscribe((value) => {
		if (value) {
			window.localStorage.setItem('access_token', value);
		} else {
			window.localStorage.removeItem('access_token');
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
	user.set(null);
}

const API_BASE_URL = 'http://localhost:8000/api';

async function apiFetch(url: string, options: RequestInit = {}) {
	const authToken = browser ? window.localStorage.getItem('access_token') : null;
	const headers = new Headers(options.headers || {});
	if (authToken) {
		headers.append('Authorization', `Bearer ${authToken}`);
	}
	if (!headers.has('Content-Type')) {
		headers.append('Content-Type', 'application/json');
	}

	const response = await fetch(`${API_BASE_URL}${url}`, {
		...options,
		headers
	});

	if (!response.ok) {
		if (response.status === 401) {
			// Token is invalid or expired
			logout();
			if (browser) {
				goto('/login');
			}
			// Throw an error to stop further processing
			throw new Error('Unauthorized');
		}

		// 嘗試從 response body 提取錯誤訊息
		let errorMessage = `API request failed: ${response.statusText}`;
		try {
			const errorData = await response.json();
			// HttpError 使用 "detail"，其他格式可能用 "message"
			errorMessage = errorData.detail || errorData.message || errorMessage;
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

export function post(url: string, data: Record<string, unknown>) {
	return apiFetch(url, {
		method: 'POST',
		body: JSON.stringify(data)
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
