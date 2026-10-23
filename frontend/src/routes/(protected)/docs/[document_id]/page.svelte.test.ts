import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/svelte';

// === Mocks (must be before component import) ===

// Mock SvelteKit modules
vi.mock('$app/stores', async () => {
	const { readable } = await import('svelte/store');
	return {
		page: readable({
			params: { document_id: 'test-doc-123' },
			url: new URL('http://localhost/docs/test-doc-123')
		})
	};
});

vi.mock('$app/navigation', () => ({
	goto: vi.fn()
}));

vi.mock('$app/environment', () => ({
	browser: true
}));

// Mock auth
vi.mock('$lib/auth', () => ({
	get: vi.fn(),
	put: vi.fn(),
	del: vi.fn(),
	post: vi.fn(),
	logout: vi.fn(),
	refreshAccessToken: vi.fn()
}));

// Mock toast
vi.mock('$lib/toast', () => ({
	toastSuccess: vi.fn(),
	toastError: vi.fn(),
	toastWarning: vi.fn()
}));

// Mock quill-delta
vi.mock('quill-delta', () => {
	class MockDelta {
		ops: unknown[];
		constructor(ops: unknown[] = []) {
			this.ops = ops;
		}
		compose(other: MockDelta) {
			return new MockDelta([...this.ops, ...(other.ops || [])]);
		}
	}
	return { default: MockDelta };
});

// QuillEditor 以 bind:this 取得實例並呼叫游標方法；mock 元件回傳的 exports 即為該實例
const quillEditorExports = vi.hoisted(() => ({
	setCursor: vi.fn(),
	removeCursor: vi.fn()
}));

// 子元件以 mock 取代；記錄各自收到的 props（Svelte 5 的 props 物件含 getter/setter，
// 可讀到頁面目前傳入的值、呼叫頁面傳入的 callback，並透過 setter 回寫 bindable prop）
const harness = vi.hoisted(() => ({
	props: {} as Record<string, Record<string, unknown>>,
	editor: null as unknown
}));

function capture(name: string, exports: Record<string, unknown> = {}) {
	return function MockComponent(_anchor: unknown, props: Record<string, unknown>) {
		harness.props[name] = props;
		if (name === 'QuillEditor' && harness.editor) {
			props.editor = harness.editor; // 等同 QuillEditor 在 onMount 建立 Quill 後回寫 bind:editor
		}
		return exports;
	};
}

vi.mock('$lib/components/QuillEditor.svelte', () => ({
	default: capture('QuillEditor', quillEditorExports)
}));

vi.mock('$lib/components/VersionHistoryPanel.svelte', () => ({
	default: capture('VersionHistoryPanel')
}));

vi.mock('$lib/components/AIDialog.svelte', () => ({
	default: capture('AIDialog')
}));

vi.mock('$lib/components/AIMetadataDialog.svelte', () => ({
	default: capture('AIMetadataDialog')
}));

vi.mock('$lib/components/AIAskDialog.svelte', () => ({
	default: capture('AIAskDialog')
}));

// 頁面以 bind:this 取得 CommentPanel 實例，把 comment_* WS 事件轉交給它
const commentPanelExports = vi.hoisted(() => ({
	addCommentFromWS: vi.fn(),
	updateCommentFromWS: vi.fn(),
	removeCommentFromWS: vi.fn()
}));

vi.mock('$lib/components/CommentPanel.svelte', () => ({
	default: capture('CommentPanel', commentPanelExports)
}));

// Import after mocks
import Page from './+page.svelte';
import { get, put, del, post, logout, refreshAccessToken } from '$lib/auth';
import { toastError, toastSuccess, toastWarning } from '$lib/toast';
import { goto } from '$app/navigation';

// Mock document data
const mockDoc = {
	title: 'Test Document',
	content: { ops: [{ insert: 'Hello\n' }] },
	is_owner: true,
	can_write: true,
	updated_at: '2026-03-07T12:00:00Z'
};

interface MockWebSocket {
	close: ReturnType<typeof vi.fn>;
	send: ReturnType<typeof vi.fn>;
	readyState: number;
	onopen: ((event: unknown) => void) | null;
	onclose: ((event: { code: number; reason: string }) => void) | null;
	onmessage: ((event: { data: string }) => void) | null;
	onerror: ((event: unknown) => void) | null;
}

// 共用的瀏覽器環境 mock（WebSocket + localStorage）
function setupBrowserMocks() {
	// Mock WebSocket
	// 注意：Vitest 4 起，被 `new` 呼叫的 mock 必須使用 function/class 實作，
	// 箭頭函式會拋出 "is not a constructor"。
	// `new` 呼叫時 vitest 回傳的是 `this` 實例而非 return 的物件，
	// 因此屬性要掛在 this 上，頁面才會在同一個物件上設定 onmessage / onclose；
	// 測試可透過 vi.mocked(WebSocket).mock.instances 取得該實例
	globalThis.WebSocket = vi.fn().mockImplementation(function (this: MockWebSocket) {
		Object.assign(this, {
			close: vi.fn(),
			send: vi.fn(),
			readyState: 1,
			onopen: null,
			onclose: null,
			onmessage: null,
			onerror: null
		});
	}) as unknown as typeof WebSocket;
	// 頁面以 readyState === WebSocket.OPEN 判斷能否送出，需與真實 WebSocket 有相同常數
	Object.assign(globalThis.WebSocket, { CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3 });

	// Mock localStorage
	const store: Record<string, string> = { access_token: 'mock-token' };
	vi.stubGlobal('localStorage', {
		getItem: vi.fn((key: string) => store[key] ?? null),
		setItem: vi.fn((key: string, val: string) => {
			store[key] = val;
		}),
		removeItem: vi.fn((key: string) => {
			delete store[key];
		})
	});
}

describe('Document Page - Load States', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		setupBrowserMocks();
	});

	it('should show loading state initially', () => {
		// API never resolves → stays in loading
		vi.mocked(get).mockImplementation(() => new Promise(() => {}));

		render(Page);

		expect(screen.getByText('Loading document...')).toBeInTheDocument();
	});

	it('should show error UI when document load fails', async () => {
		vi.mocked(get).mockRejectedValue(new Error('Document not found'));

		render(Page);

		await waitFor(() => {
			expect(screen.getByTestId('error-state')).toBeInTheDocument();
			expect(screen.getByRole('heading', { name: 'Failed to load document' })).toBeInTheDocument();
			expect(screen.getByText('Document not found')).toBeInTheDocument();
		});
	});

	it('should show retry button and back link on error', async () => {
		vi.mocked(get).mockRejectedValue(new Error('Server error'));

		render(Page);

		await waitFor(() => {
			expect(screen.getByText('Retry')).toBeInTheDocument();
			const backLink = screen.getByText('Back to Dashboard');
			expect(backLink).toBeInTheDocument();
			expect(backLink.closest('a')).toHaveAttribute('href', '/dashboard');
		});
	});

	it('should show toast notification on load error', async () => {
		vi.mocked(get).mockRejectedValue(new Error('Network error'));

		render(Page);

		await waitFor(() => {
			expect(toastError).toHaveBeenCalledWith('Network error');
		});
	});

	it('should retry loading when retry button is clicked', async () => {
		vi.mocked(get).mockRejectedValueOnce(new Error('Network error')).mockResolvedValueOnce(mockDoc);

		render(Page);

		// Wait for error state
		await waitFor(() => {
			expect(screen.getByTestId('error-state')).toBeInTheDocument();
		});

		// Click retry
		await fireEvent.click(screen.getByText('Retry'));

		// Should call get twice (initial + retry) and resolve successfully
		expect(get).toHaveBeenCalledTimes(2);
		await waitFor(() => {
			expect(screen.queryByTestId('error-state')).toBeNull();
			expect(screen.queryByTestId('loading-state')).toBeNull();
		});
	});

	it('should hide error UI after successful retry', async () => {
		vi.mocked(get).mockRejectedValueOnce(new Error('Network error')).mockResolvedValueOnce(mockDoc);

		render(Page);

		// Wait for error state
		await waitFor(() => {
			expect(screen.getByTestId('error-state')).toBeInTheDocument();
		});

		// Click retry
		await fireEvent.click(screen.getByText('Retry'));

		// Error UI should disappear
		await waitFor(() => {
			expect(screen.queryByTestId('error-state')).toBeNull();
			expect(screen.queryByTestId('loading-state')).toBeNull();
		});
	});

	it('should not show loading or error after successful load', async () => {
		vi.mocked(get).mockResolvedValue(mockDoc);

		render(Page);

		await waitFor(() => {
			expect(screen.queryByTestId('loading-state')).toBeNull();
			expect(screen.queryByTestId('error-state')).toBeNull();
		});
	});

	it('should handle non-Error exceptions gracefully', async () => {
		vi.mocked(get).mockRejectedValue('string error');

		render(Page);

		await waitFor(() => {
			expect(screen.getByTestId('error-state')).toBeInTheDocument();
			// Falls back to default message
			expect(screen.getByText('Failed to load document.')).toBeInTheDocument();
		});
	});
});

describe('Document Page - Collaborator Permission Update', () => {
	const mockCollaborator = {
		id: 2,
		username: 'alice',
		email: 'alice@example.com',
		permission: 'write'
	};

	beforeEach(() => {
		vi.clearAllMocks();
		setupBrowserMocks();

		// 文檔載入與協作者列表都走 get，依 URL 區分
		vi.mocked(get).mockImplementation((url: string) => {
			if (url.includes('/collaborators/')) {
				return Promise.resolve([{ ...mockCollaborator }]);
			}
			return Promise.resolve(mockDoc);
		});
	});

	async function openShareModalAndGetSelect(): Promise<HTMLSelectElement> {
		render(Page);

		// 等文檔載入完成後打開 Share modal
		await waitFor(() => {
			expect(screen.getByTitle('Share')).toBeInTheDocument();
		});
		await fireEvent.click(screen.getByTitle('Share'));

		// 等協作者列表載入，取得該協作者的權限下拉選單
		return (await screen.findByLabelText('Change permission for alice')) as HTMLSelectElement;
	}

	it('should update permission via PUT and reflect new value', async () => {
		vi.mocked(put).mockResolvedValue({ ...mockCollaborator, permission: 'read' });

		const select = await openShareModalAndGetSelect();
		expect(select.value).toBe('write');

		await fireEvent.change(select, { target: { value: 'read' } });

		await waitFor(() => {
			expect(put).toHaveBeenCalledWith('/documents/test-doc-123/collaborators/2/', {
				permission: 'read'
			});
			expect(toastSuccess).toHaveBeenCalledWith('alice can now only view this document.');
			expect(select.value).toBe('read');
		});
	});

	it('should revert select value and show error toast when PUT fails', async () => {
		vi.mocked(put).mockRejectedValue(new Error('Server error'));

		const select = await openShareModalAndGetSelect();

		await fireEvent.change(select, { target: { value: 'read' } });

		await waitFor(() => {
			expect(toastError).toHaveBeenCalledWith('Failed to update permission.');
			// 失敗後下拉選單還原為原本的權限
			expect(select.value).toBe('write');
		});
	});

	it('should not call PUT when the selected permission is unchanged', async () => {
		const select = await openShareModalAndGetSelect();

		await fireEvent.change(select, { target: { value: 'write' } });

		expect(put).not.toHaveBeenCalled();
	});
});

describe('Document Page - Save', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		setupBrowserMocks();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('should PUT only the title when content was not edited locally', async () => {
		// 遠端 delta 以 silent 套用不會更新綁定的 content；若單改標題也送 content，
		// 會把過期快照寫回 DB 蓋掉協作者的內容
		vi.mocked(get).mockResolvedValue(mockDoc);
		vi.mocked(put).mockResolvedValue({});

		render(Page);
		const titleInput = await screen.findByPlaceholderText('Untitled Document');

		vi.useFakeTimers();
		await fireEvent.input(titleInput, { target: { value: 'Renamed' } });
		await vi.advanceTimersByTimeAsync(1500);

		expect(put).toHaveBeenCalledTimes(1);
		expect(put).toHaveBeenCalledWith('/documents/test-doc-123/', { title: 'Renamed' });
	});
});

describe('Document Page - WebSocket close handling', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		setupBrowserMocks();
	});

	it('should surface the connection_error message when the backend closes without a reason', async () => {
		// 後端先送 connection_error 再 close(code)，close frame 沒有 reason，
		// 具體原因（如被移除協作資格）必須靠暫存的 connection_error 訊息顯示
		vi.mocked(get).mockResolvedValue(mockDoc);
		render(Page);

		await waitFor(() => expect(globalThis.WebSocket).toHaveBeenCalled());
		const ws = vi.mocked(globalThis.WebSocket).mock.instances[0] as unknown as MockWebSocket;
		expect(ws.onmessage).toBeTypeOf('function');

		ws.onmessage!({
			data: JSON.stringify({
				type: 'connection_error',
				error_code: 'PERMISSION_DENIED',
				message: 'Your access to this document has been removed'
			})
		});
		ws.onclose!({ code: 4003, reason: '' });

		expect(toastError).toHaveBeenCalledWith('Your access to this document has been removed');
		expect(goto).toHaveBeenCalledWith('/dashboard');
	});
});

describe('Document Page - WebSocket protocol', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		setupBrowserMocks();
		vi.mocked(get).mockResolvedValue(mockDoc);
	});

	afterEach(() => {
		vi.useRealTimers();
		vi.restoreAllMocks();
	});

	function sockets(): MockWebSocket[] {
		return vi.mocked(globalThis.WebSocket).mock.instances as unknown as MockWebSocket[];
	}

	async function connect(): Promise<MockWebSocket> {
		render(Page);
		await waitFor(() => expect(globalThis.WebSocket).toHaveBeenCalled());
		const ws = sockets().at(-1)!;
		ws.onopen!({});
		return ws;
	}

	function receive(ws: MockWebSocket, data: Record<string, unknown>) {
		ws.onmessage!({ data: JSON.stringify(data) });
	}

	it('opens the socket with the access token as a subprotocol', async () => {
		await connect();

		expect(globalThis.WebSocket).toHaveBeenCalledWith(
			`ws://${window.location.host}/ws/docs/test-doc-123/`,
			['access_token.mock-token']
		);
	});

	it('applies can_write from connection_success', async () => {
		const ws = await connect();
		expect(screen.queryByText('View Only')).toBeNull();

		receive(ws, { type: 'connection_success', can_write: false, user_id: '1' });

		expect(await screen.findByText('View Only')).toBeInTheDocument();
		expect(screen.getByPlaceholderText('Untitled Document')).toBeDisabled();
	});

	it('permission_update notifies about promotion and demotion', async () => {
		const ws = await connect();

		receive(ws, { type: 'permission_update', can_write: false });
		expect(toastWarning).toHaveBeenCalledWith('Your access has been changed to read-only.');
		expect(await screen.findByText('View Only')).toBeInTheDocument();

		receive(ws, { type: 'permission_update', can_write: true });
		expect(toastSuccess).toHaveBeenCalledWith('You now have edit access to this document.');
		await waitFor(() => expect(screen.queryByText('View Only')).toBeNull());
	});

	it('doc_saved shows the last save time when idle', async () => {
		const ws = await connect();
		const savedAt = '2026-03-08T09:30:00Z';

		receive(ws, { type: 'doc_saved', updated_at: savedAt });

		expect(
			await screen.findByText(`Last save at ${new Date(savedAt).toLocaleTimeString()}`)
		).toBeInTheDocument();
	});

	it('doc_saved confirms an in-flight save, then returns to idle', async () => {
		vi.mocked(put).mockImplementation(() => new Promise(() => {}));
		const ws = await connect();
		const titleInput = screen.getByPlaceholderText('Untitled Document');

		vi.useFakeTimers();
		await fireEvent.input(titleInput, { target: { value: 'Renamed' } });
		expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
		await vi.advanceTimersByTimeAsync(1500);
		expect(screen.getByText('Saving...')).toBeInTheDocument();

		receive(ws, { type: 'doc_saved', updated_at: '2026-03-08T09:30:00Z' });
		await vi.advanceTimersByTimeAsync(0);
		expect(screen.getByText('All changes saved')).toBeInTheDocument();

		await vi.advanceTimersByTimeAsync(2000);
		expect(screen.getByText(/^Last save at /)).toBeInTheDocument();
	});

	it('doc_restored by another user warns with who and which version', async () => {
		const ws = await connect();
		receive(ws, { type: 'connection_success', can_write: true, user_id: '1' });

		receive(ws, {
			type: 'doc_restored',
			content: { ops: [{ insert: 'old\n' }] },
			updated_at: '2026-03-08T09:30:00Z',
			restored_by: '2',
			restored_by_username: 'alice',
			restored_to_version: 3,
			new_version_number: 5
		});

		expect(toastWarning).toHaveBeenCalledWith('alice 已將文件還原到版本 3');
		expect(await screen.findByText('All changes saved')).toBeInTheDocument();
	});

	it('doc_restored by the current user does not warn again', async () => {
		const ws = await connect();
		receive(ws, { type: 'connection_success', can_write: true, user_id: '1' });

		receive(ws, {
			type: 'doc_restored',
			content: { ops: [{ insert: 'old\n' }] },
			updated_at: '2026-03-08T09:30:00Z',
			restored_by: '1',
			restored_by_username: 'me',
			restored_to_version: 3,
			new_version_number: 5
		});

		expect(toastWarning).not.toHaveBeenCalled();
	});

	it('tracks online users from presence_sync, user_join and user_leave (excluding self)', async () => {
		const ws = await connect();
		receive(ws, { type: 'connection_success', can_write: true, user_id: '1' });

		receive(ws, {
			type: 'presence_sync',
			users: [
				{ user_id: '1', username: 'me', color: '#111111' },
				{ user_id: '2', username: 'alice', color: '#222222' }
			]
		});
		const alice = await screen.findByTitle('alice');
		expect(alice).toHaveTextContent('A');
		expect(alice).toHaveStyle({ backgroundColor: '#222222' });
		expect(screen.queryByTitle('me')).toBeNull();

		receive(ws, { type: 'user_join', user_id: '3', username: 'bob', color: '#333333' });
		expect(await screen.findByTitle('bob')).toHaveTextContent('B');

		receive(ws, { type: 'user_leave', user_id: '2' });
		await waitFor(() => expect(screen.queryByTitle('alice')).toBeNull());
		expect(screen.getByTitle('bob')).toBeInTheDocument();
		expect(quillEditorExports.removeCursor).toHaveBeenCalledWith('2');
	});

	it('forwards remote cursors to the editor', async () => {
		const ws = await connect();
		const cursor = { index: 4, length: 2 };

		receive(ws, { type: 'cursor_move', user_id: '2', username: 'alice', color: '#222222', cursor });

		expect(quillEditorExports.setCursor).toHaveBeenCalledWith('2', 'alice', '#222222', cursor);
	});

	it.each([
		[{ error_code: 'RATE_LIMITED', retry_after: 2.2 }, 'warning', 'Too fast! Wait 3s'],
		[{ error_code: 'READ_ONLY' }, 'warning', 'You have read-only access to this document.'],
		[
			{ error_code: 'INVALID_JSON', message: 'Invalid JSON format' },
			'error',
			'Invalid JSON format'
		],
		[{ error_code: 'UNKNOWN' }, 'error', 'An error occurred.']
	])('runtime error %o is shown as %s', async (payload, level, expected) => {
		const ws = await connect();

		receive(ws, { type: 'error', ...payload });

		const toast = level === 'warning' ? toastWarning : toastError;
		expect(toast).toHaveBeenCalledWith(expected);
	});

	it('ai_stream_error falls back to a default message', async () => {
		const ws = await connect();

		receive(ws, { type: 'ai_stream_error', message: 'AI 服務未配置' });
		receive(ws, { type: 'ai_stream_error' });

		expect(toastError).toHaveBeenNthCalledWith(1, 'AI 服務未配置');
		expect(toastError).toHaveBeenNthCalledWith(2, 'AI 串流失敗');
	});

	describe('close codes', () => {
		it('does nothing on a normal close', async () => {
			const ws = await connect();
			vi.useFakeTimers();

			ws.onclose!({ code: 1000, reason: '' });
			await vi.advanceTimersByTimeAsync(60000);

			expect(sockets()).toHaveLength(1);
			expect(toastError).not.toHaveBeenCalled();
		});

		it('4001 logs out and redirects to login', async () => {
			const ws = await connect();

			ws.onclose!({ code: 4001, reason: '' });

			expect(toastError).toHaveBeenCalledWith('Session expired. Please login again.');
			expect(logout).toHaveBeenCalled();
			expect(goto).toHaveBeenCalledWith('/login');
			expect(await screen.findByText('Error saving document')).toBeInTheDocument();
		});

		it('4002 refreshes the token and reconnects', async () => {
			vi.mocked(refreshAccessToken).mockResolvedValue(true);
			vi.spyOn(Math, 'random').mockReturnValue(0);
			const ws = await connect();
			vi.useFakeTimers();

			ws.onclose!({ code: 4002, reason: '' });
			await vi.advanceTimersByTimeAsync(999);
			expect(sockets()).toHaveLength(1);
			await vi.advanceTimersByTimeAsync(1);

			expect(refreshAccessToken).toHaveBeenCalled();
			expect(sockets()).toHaveLength(2);
			expect(logout).not.toHaveBeenCalled();
		});

		it('4002 logs out when the token cannot be refreshed', async () => {
			vi.mocked(refreshAccessToken).mockResolvedValue(false);
			const ws = await connect();

			ws.onclose!({ code: 4002, reason: '' });

			await waitFor(() => expect(goto).toHaveBeenCalledWith('/login'));
			expect(toastError).toHaveBeenCalledWith('Session expired. Please login again.');
			expect(logout).toHaveBeenCalled();
		});

		it('4003 without a backend message uses the default text', async () => {
			const ws = await connect();

			ws.onclose!({ code: 4003, reason: '' });

			expect(toastError).toHaveBeenCalledWith(
				'You do not have permission to access this document.'
			);
			expect(goto).toHaveBeenCalledWith('/dashboard');
		});

		it('4004 goes back to the dashboard', async () => {
			const ws = await connect();

			ws.onclose!({ code: 4004, reason: '' });

			expect(toastError).toHaveBeenCalledWith('Document not found.');
			expect(goto).toHaveBeenCalledWith('/dashboard');
		});

		it('4005 asks to close tabs without navigating or reconnecting', async () => {
			const ws = await connect();
			vi.useFakeTimers();

			ws.onclose!({ code: 4005, reason: '' });
			await vi.advanceTimersByTimeAsync(60000);

			expect(toastError).toHaveBeenCalledWith('Too many open tabs. Please close some and refresh.');
			expect(goto).not.toHaveBeenCalled();
			expect(sockets()).toHaveLength(1);
		});

		it('other application codes surface the close reason', async () => {
			const ws = await connect();

			ws.onclose!({ code: 4999, reason: 'Custom reason' });

			expect(toastError).toHaveBeenCalledWith('Custom reason');
		});

		it('transient closes reconnect with exponential backoff and restore notice', async () => {
			vi.spyOn(Math, 'random').mockReturnValue(0);
			const ws = await connect();
			vi.useFakeTimers();

			// 第 1 次：1s 後重連
			ws.onclose!({ code: 1006, reason: '' });
			await vi.advanceTimersByTimeAsync(0);
			expect(screen.getByText('Connecting...')).toBeInTheDocument();
			await vi.advanceTimersByTimeAsync(999);
			expect(sockets()).toHaveLength(1);
			await vi.advanceTimersByTimeAsync(1);
			expect(sockets()).toHaveLength(2);

			// 第 2 次（尚未收到 connection_success）：退避加倍為 2s
			sockets()[1].onclose!({ code: 1006, reason: '' });
			await vi.advanceTimersByTimeAsync(1999);
			expect(sockets()).toHaveLength(2);
			await vi.advanceTimersByTimeAsync(1);
			expect(sockets()).toHaveLength(3);

			// 重連成功才歸零並提示
			receive(sockets()[2], { type: 'connection_success', can_write: true, user_id: '1' });
			expect(toastSuccess).toHaveBeenCalledWith('Connection restored.');
		});

		it('jitter adds up to 50% to the backoff delay', async () => {
			vi.spyOn(Math, 'random').mockReturnValue(0.5);
			const ws = await connect();
			vi.useFakeTimers();

			ws.onclose!({ code: 1006, reason: '' });
			await vi.advanceTimersByTimeAsync(1249);
			expect(sockets()).toHaveLength(1);
			await vi.advanceTimersByTimeAsync(1);
			expect(sockets()).toHaveLength(2);
		});

		it('gives up after 5 failed reconnect attempts', async () => {
			vi.spyOn(Math, 'random').mockReturnValue(0);
			const ws = await connect();
			vi.useFakeTimers();

			ws.onclose!({ code: 1006, reason: '' });
			for (let attempt = 1; attempt <= 5; attempt++) {
				await vi.advanceTimersByTimeAsync(30000);
				expect(sockets()).toHaveLength(attempt + 1);
				sockets().at(-1)!.onclose!({ code: 1006, reason: '' });
			}
			await vi.advanceTimersByTimeAsync(60000);

			expect(sockets()).toHaveLength(6);
			expect(toastError).toHaveBeenCalledWith('Connection lost. Please refresh the page.');
			expect(screen.getByText('Error saving document')).toBeInTheDocument();
		});
	});
});

describe('Document Page - initial permissions and cleanup', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		setupBrowserMocks();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('hides owner actions unless is_owner is exactly true', async () => {
		vi.mocked(get).mockResolvedValue({ ...mockDoc, is_owner: 'yes' });

		render(Page);

		await screen.findByPlaceholderText('Untitled Document');
		expect(screen.queryByTitle('Share')).toBeNull();
		expect(screen.queryByTitle('Delete')).toBeNull();
	});

	it('shows owner actions for the owner', async () => {
		vi.mocked(get).mockResolvedValue(mockDoc);

		render(Page);

		expect(await screen.findByTitle('Share')).toBeInTheDocument();
		expect(screen.getByTitle('Delete')).toBeInTheDocument();
	});

	it('starts read-only only when the API says can_write is false', async () => {
		vi.mocked(get).mockResolvedValue({ ...mockDoc, is_owner: false, can_write: false });
		render(Page);
		expect(await screen.findByText('View Only')).toBeInTheDocument();
		expect(screen.getByPlaceholderText('Untitled Document')).toBeDisabled();
	});

	it('treats a missing can_write as writable', async () => {
		const { can_write: _ignored, ...withoutFlag } = mockDoc;
		vi.mocked(get).mockResolvedValue({ ...withoutFlag, is_owner: false });
		render(Page);
		const title = await screen.findByPlaceholderText('Untitled Document');
		expect(title).not.toBeDisabled();
		expect(screen.queryByText('View Only')).toBeNull();
	});

	it('closes the socket without reconnecting when leaving the page', async () => {
		vi.mocked(get).mockResolvedValue(mockDoc);
		const { unmount } = render(Page);
		await waitFor(() => expect(globalThis.WebSocket).toHaveBeenCalled());
		const ws = vi.mocked(globalThis.WebSocket).mock.instances[0] as unknown as MockWebSocket;
		vi.useFakeTimers();

		unmount();
		await vi.advanceTimersByTimeAsync(60000);

		expect(ws.close).toHaveBeenCalled();
		expect(ws.onclose).toBeNull();
		expect(globalThis.WebSocket).toHaveBeenCalledTimes(1);
	});
});

// ── 依賴 Quill 實例的編輯流程（假 editor 透過 bind:editor 回寫給頁面）──

function createFakeEditor(initialText = 'Hello world\n') {
	let text = initialText;
	return {
		selection: null as { index: number; length: number } | null,
		getSelection: vi.fn(function (this: { selection: unknown }) {
			return this.selection;
		}),
		getText: vi.fn((index?: number, length?: number) =>
			index === undefined ? text : text.slice(index, index + (length ?? text.length))
		),
		getFormat: vi.fn(() => ({ bold: true })),
		deleteText: vi.fn((index: number, length: number) => {
			text = text.slice(0, index) + text.slice(index + length);
		}),
		insertText: vi.fn((index: number, value: string) => {
			text = text.slice(0, index) + value + text.slice(index);
		}),
		getContents: vi.fn(() => ({ ops: [{ insert: text }] })),
		setContents: vi.fn(),
		updateContents: vi.fn(),
		setText(value: string) {
			text = value;
		}
	};
}

describe('Document Page - editing with the editor instance', () => {
	let editor: ReturnType<typeof createFakeEditor>;

	beforeEach(() => {
		vi.clearAllMocks();
		setupBrowserMocks();
		vi.mocked(get).mockResolvedValue(mockDoc);
		editor = createFakeEditor();
		harness.editor = editor;
		harness.props = {};
	});

	afterEach(() => {
		vi.useRealTimers();
		harness.editor = null;
	});

	async function ready() {
		render(Page);
		await waitFor(() => expect(globalThis.WebSocket).toHaveBeenCalled());
		await waitFor(() => expect(harness.props.QuillEditor).toBeDefined());
		const ws = vi.mocked(globalThis.WebSocket).mock.instances[0] as unknown as MockWebSocket;
		ws.onopen!({});
		return ws;
	}

	function quill() {
		return harness.props.QuillEditor as {
			onTextChange: (d: { delta: unknown; source: string }) => void;
			onSelectionChange: (r: { index: number; length: number } | null) => void;
		};
	}

	function sent(ws: MockWebSocket) {
		return ws.send.mock.calls.map(([raw]) => JSON.parse(raw as string));
	}

	function receive(ws: MockWebSocket, data: Record<string, unknown>) {
		ws.onmessage!({ data: JSON.stringify(data) });
	}

	it('applies remote deltas and restored content silently', async () => {
		const ws = await ready();
		const delta = { ops: [{ retain: 1 }, { insert: 'x' }] };

		receive(ws, { type: 'doc_update', delta });
		receive(ws, {
			type: 'doc_restored',
			content: { ops: [{ insert: 'old\n' }] },
			updated_at: '2026-03-08T09:30:00Z',
			restored_by: '2',
			restored_by_username: 'alice',
			restored_to_version: 1,
			new_version_number: 2
		});

		expect(editor.updateContents).toHaveBeenCalledWith(delta, 'silent');
		expect(editor.setContents).toHaveBeenCalledWith([{ insert: 'old\n' }], 'silent');
	});

	it('sends local edits immediately, then throttles and composes bursts', async () => {
		const ws = await ready();
		vi.useFakeTimers();

		quill().onTextChange({ delta: { ops: [{ insert: 'a' }] }, source: 'user' });
		expect(sent(ws)).toEqual([{ delta: { ops: [{ insert: 'a' }] } }]);

		quill().onTextChange({ delta: { ops: [{ insert: 'b' }] }, source: 'user' });
		quill().onTextChange({ delta: { ops: [{ insert: 'c' }] }, source: 'user' });
		expect(sent(ws)).toHaveLength(1);

		await vi.advanceTimersByTimeAsync(150);
		expect(sent(ws)).toEqual([
			{ delta: { ops: [{ insert: 'a' }] } },
			{ delta: { ops: [{ insert: 'b' }, { insert: 'c' }] } }
		]);
	});

	it('ignores non-user changes', async () => {
		const ws = await ready();
		vi.useFakeTimers();

		quill().onTextChange({ delta: { ops: [{ insert: 'remote' }] }, source: 'api' });
		await vi.advanceTimersByTimeAsync(2000);

		expect(ws.send).not.toHaveBeenCalled();
		expect(put).not.toHaveBeenCalled();
	});

	it('saves edited content from the editor after the debounce', async () => {
		vi.mocked(put).mockResolvedValue({});
		await ready();
		vi.useFakeTimers();

		quill().onTextChange({ delta: { ops: [{ insert: '!' }] }, source: 'user' });
		await vi.advanceTimersByTimeAsync(1499);
		expect(put).not.toHaveBeenCalled();
		await vi.advanceTimersByTimeAsync(1);

		expect(put).toHaveBeenCalledWith('/documents/test-doc-123/', {
			title: 'Test Document',
			content: { ops: [{ insert: 'Hello world\n' }] }
		});
	});

	it('keeps content dirty after a failed save so the next save resends it', async () => {
		vi.mocked(put).mockRejectedValueOnce(new Error('offline')).mockResolvedValue({});
		await ready();
		const title = screen.getByPlaceholderText('Untitled Document');
		vi.useFakeTimers();

		quill().onTextChange({ delta: { ops: [{ insert: '!' }] }, source: 'user' });
		await vi.advanceTimersByTimeAsync(1500);
		expect(toastError).toHaveBeenCalledWith('Failed to save document.');

		await fireEvent.input(title, { target: { value: 'Renamed' } });
		await vi.advanceTimersByTimeAsync(1500);

		expect(put).toHaveBeenLastCalledWith('/documents/test-doc-123/', {
			title: 'Renamed',
			content: { ops: [{ insert: 'Hello world\n' }] }
		});
	});

	it('throttles cursor updates to the latest position', async () => {
		const ws = await ready();
		vi.useFakeTimers();

		quill().onSelectionChange({ index: 1, length: 0 });
		quill().onSelectionChange({ index: 4, length: 2 });
		expect(ws.send).not.toHaveBeenCalled();
		await vi.advanceTimersByTimeAsync(150);

		expect(sent(ws)).toEqual([{ type: 'cursor_move', index: 4, length: 2 }]);
	});

	it('does not send cursors for read-only users or empty selections', async () => {
		const ws = await ready();
		vi.useFakeTimers();

		quill().onSelectionChange(null);
		receive(ws, { type: 'permission_update', can_write: false });
		quill().onSelectionChange({ index: 1, length: 0 });
		await vi.advanceTimersByTimeAsync(500);

		expect(ws.send).not.toHaveBeenCalled();
	});

	describe('AI writing assistant', () => {
		function aiDialog() {
			return harness.props.AIDialog as {
				isOpen: boolean;
				selectedText: string;
				streaming: boolean;
				streamText: string;
				onApply: (text: string) => void;
				onStream: (action: string, text: string) => boolean;
				onCancelStream: () => void;
			};
		}

		it('requires a selection before opening', async () => {
			await ready();

			await fireEvent.click(screen.getByTitle('AI Writing Assistant'));

			expect(toastWarning).toHaveBeenCalledWith('Please select text first');
			expect(aiDialog().isOpen).toBe(false);
		});

		it('replaces the selected text while keeping its formatting', async () => {
			await ready();
			editor.selection = { index: 6, length: 5 };

			await fireEvent.click(screen.getByTitle('AI Writing Assistant'));
			expect(aiDialog().isOpen).toBe(true);
			expect(aiDialog().selectedText).toBe('world');

			aiDialog().onApply('there');

			expect(editor.getFormat).toHaveBeenCalledWith(6, 5);
			expect(editor.deleteText).toHaveBeenCalledWith(6, 5, 'user');
			expect(editor.insertText).toHaveBeenCalledWith(6, 'there', { bold: true }, 'user');
		});

		it('refuses to apply when collaborators changed the selected text', async () => {
			await ready();
			editor.selection = { index: 6, length: 5 };
			await fireEvent.click(screen.getByTitle('AI Writing Assistant'));

			editor.setText('Hello WORLD\n');
			aiDialog().onApply('there');

			expect(toastWarning).toHaveBeenCalledWith('Text was modified. Please reselect.');
			expect(editor.deleteText).not.toHaveBeenCalled();
		});

		it('streams over the socket and accumulates chunks', async () => {
			const ws = await ready();

			expect(aiDialog().onStream('polish', 'abc')).toBe(true);
			expect(sent(ws)).toEqual([{ type: 'ai_stream', action: 'polish', text: 'abc' }]);
			receive(ws, { type: 'ai_stream_start', action: 'polish' });
			receive(ws, { type: 'ai_stream_chunk', chunk: '潤' });
			receive(ws, { type: 'ai_stream_chunk', chunk: '飾' });
			await waitFor(() => expect(aiDialog().streamText).toBe('潤飾'));
			expect(aiDialog().streaming).toBe(true);

			receive(ws, { type: 'ai_stream_end', action: 'polish' });
			await waitFor(() => expect(aiDialog().streaming).toBe(false));
		});

		it('cancels a running stream over the socket', async () => {
			const ws = await ready();
			aiDialog().onStream('summarize', 'abc');

			aiDialog().onCancelStream();

			expect(sent(ws).at(-1)).toEqual({ type: 'ai_stream_cancel' });
			await waitFor(() => expect(aiDialog().streaming).toBe(false));
		});

		it('refuses to stream when the socket is not open', async () => {
			const ws = await ready();
			ws.readyState = 3; // CLOSED

			expect(aiDialog().onStream('summarize', 'abc')).toBe(false);

			expect(toastError).toHaveBeenCalledWith('連線中斷，無法使用 AI 串流');
			expect(ws.send).not.toHaveBeenCalled();
		});
	});

	describe('whole-document AI dialogs', () => {
		it.each([
			['文件分析', 'AIMetadataDialog'],
			['文件問答', 'AIAskDialog']
		])('%s warns on an empty document', async (title, dialog) => {
			editor.setText('  \n');
			await ready();

			await fireEvent.click(screen.getByTitle(title));

			expect(toastWarning).toHaveBeenCalledWith('文件目前是空的');
			expect(harness.props[dialog].isOpen).toBe(false);
		});

		it.each([
			['文件分析', 'AIMetadataDialog'],
			['文件問答', 'AIAskDialog']
		])('%s opens with the full document text', async (title, dialog) => {
			await ready();

			await fireEvent.click(screen.getByTitle(title));

			expect(harness.props[dialog].isOpen).toBe(true);
			expect(harness.props[dialog].documentText).toBe('Hello world\n');
		});

		it('asks questions over the socket with the document text', async () => {
			const ws = await ready();
			const ask = harness.props.AIAskDialog as { onAsk: (q: string, t: string) => boolean };

			expect(ask.onAsk('重點？', '全文')).toBe(true);

			expect(sent(ws)).toEqual([
				{ type: 'ai_ask_stream', question: '重點？', document_text: '全文' }
			]);
		});
	});

	it('reloads the document into the editor after a version restore', async () => {
		await ready();
		vi.mocked(get).mockResolvedValue({
			...mockDoc,
			title: 'Restored',
			content: { ops: [{ insert: 'v1\n' }] },
			updated_at: '2026-03-09T09:00:00Z'
		});

		await (harness.props.VersionHistoryPanel as { onRestore: () => Promise<void> }).onRestore();

		expect(editor.setContents).toHaveBeenCalledWith([{ insert: 'v1\n' }], 'silent');
		expect(await screen.findByDisplayValue('Restored')).toBeInTheDocument();
		expect(screen.getByText('All changes saved')).toBeInTheDocument();
	});
});

describe('Document Page - sharing and deleting', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		setupBrowserMocks();
		harness.editor = null;
		vi.mocked(get).mockImplementation((url: string) =>
			Promise.resolve(
				url.includes('/collaborators/')
					? [{ id: 2, username: 'alice', email: 'alice@example.com', permission: 'write' }]
					: mockDoc
			)
		);
	});

	async function openShare() {
		render(Page);
		await fireEvent.click(await screen.findByTitle('Share'));
		await screen.findByLabelText('Change permission for alice');
	}

	it('adds a collaborator with the chosen permission and resets the form', async () => {
		vi.mocked(post).mockResolvedValue({
			id: 3,
			username: 'bob',
			email: null,
			permission: 'read'
		});
		await openShare();
		const input = screen.getByPlaceholderText('Enter username') as HTMLInputElement;

		await fireEvent.input(input, { target: { value: 'bob' } });
		await fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'read' } });
		await fireEvent.click(screen.getByText('Add'));

		await waitFor(() =>
			expect(toastSuccess).toHaveBeenCalledWith('Successfully added bob as a collaborator.')
		);
		expect(post).toHaveBeenCalledWith('/documents/test-doc-123/collaborators/', {
			username: 'bob',
			permission: 'read'
		});
		expect(await screen.findByLabelText('Change permission for bob')).toBeInTheDocument();
		expect(input.value).toBe('');
		expect((screen.getAllByRole('combobox')[0] as HTMLSelectElement).value).toBe('write');
	});

	it('does not submit an empty username and shows backend errors', async () => {
		await openShare();
		await fireEvent.click(screen.getByText('Add'));
		expect(post).not.toHaveBeenCalled();

		vi.mocked(post).mockRejectedValue(new Error('No User matches the given query.'));
		await fireEvent.input(screen.getByPlaceholderText('Enter username'), {
			target: { value: 'ghost' }
		});
		await fireEvent.click(screen.getByText('Add'));

		await waitFor(() =>
			expect(toastError).toHaveBeenCalledWith('No User matches the given query.')
		);
	});

	it('removes a collaborator after confirmation', async () => {
		vi.mocked(del).mockResolvedValue(null);
		await openShare();

		await fireEvent.click(screen.getByTitle('Remove collaborator'));
		expect(screen.getByText('alice', { selector: 'strong' })).toBeInTheDocument();
		await fireEvent.click(screen.getByText('Remove'));

		await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('Collaborator removed.'));
		expect(del).toHaveBeenCalledWith('/documents/test-doc-123/collaborators/2/');
		expect(screen.queryByLabelText('Change permission for alice')).toBeNull();
		expect(screen.queryByText('Remove Collaborator')).toBeNull();
	});

	it('keeps the collaborator when removal fails', async () => {
		vi.mocked(del).mockRejectedValue(new Error('boom'));
		await openShare();

		await fireEvent.click(screen.getByTitle('Remove collaborator'));
		await fireEvent.click(screen.getByText('Remove'));

		await waitFor(() => expect(toastError).toHaveBeenCalledWith('Failed to remove collaborator.'));
		expect(screen.getByLabelText('Change permission for alice')).toBeInTheDocument();
	});

	it('deletes the document after confirmation and returns to the dashboard', async () => {
		vi.mocked(del).mockResolvedValue(null);
		render(Page);

		await fireEvent.click(await screen.findByTitle('Delete'));
		await fireEvent.click(within(screen.getByRole('alertdialog')).getByText('刪除'));

		await waitFor(() => expect(goto).toHaveBeenCalledWith('/dashboard'));
		expect(del).toHaveBeenCalledWith('/documents/test-doc-123/');
		expect(toastSuccess).toHaveBeenCalledWith('文件已成功刪除');
	});

	it('stays on the page when deleting fails', async () => {
		vi.mocked(del).mockRejectedValue(new Error('boom'));
		render(Page);

		await fireEvent.click(await screen.findByTitle('Delete'));
		await fireEvent.click(within(screen.getByRole('alertdialog')).getByText('刪除'));

		await waitFor(() => expect(toastError).toHaveBeenCalledWith('刪除文件失敗'));
		expect(goto).not.toHaveBeenCalled();
	});
});

describe('Document Page - edit state, socket guards and cleanup', () => {
	let editor: ReturnType<typeof createFakeEditor>;

	beforeEach(() => {
		vi.clearAllMocks();
		setupBrowserMocks();
		vi.mocked(get).mockResolvedValue(mockDoc);
		editor = createFakeEditor();
		harness.editor = editor;
		harness.props = {};
	});

	afterEach(() => {
		vi.useRealTimers();
		vi.restoreAllMocks();
		harness.editor = null;
	});

	async function ready() {
		const view = render(Page);
		await waitFor(() => expect(globalThis.WebSocket).toHaveBeenCalled());
		await waitFor(() => expect(harness.props.QuillEditor).toBeDefined());
		const ws = vi.mocked(globalThis.WebSocket).mock.instances[0] as unknown as MockWebSocket;
		ws.onopen!({});
		return { ws, unmount: view.unmount };
	}

	function quill() {
		return harness.props.QuillEditor as {
			value: unknown;
			onTextChange: (d: { delta: unknown; source: string }) => void;
			onSelectionChange: (r: { index: number; length: number } | null) => void;
		};
	}

	function type(text: string) {
		quill().onTextChange({ delta: { ops: [{ insert: text }] }, source: 'user' });
	}

	function sent(ws: MockWebSocket) {
		return ws.send.mock.calls.map(([raw]) => JSON.parse(raw as string));
	}

	function receive(ws: MockWebSocket, data: Record<string, unknown>) {
		ws.onmessage!({ data: JSON.stringify(data) });
	}

	function status() {
		return document.querySelector('.doc-status')!.textContent;
	}

	const lastSaveAt = (iso: string) => `Last save at ${new Date(iso).toLocaleTimeString()}`;

	describe('loading', () => {
		it('hands the loaded content to the editor, or an empty delta when there is none', async () => {
			await ready();
			expect(quill().value).toEqual(mockDoc.content);

			const { content: _ignored, ...withoutContent } = mockDoc;
			vi.mocked(get).mockResolvedValue(withoutContent);
			harness.props = {};
			render(Page);
			await waitFor(() => expect(harness.props.QuillEditor).toBeDefined());
			expect(quill().value).toEqual({ ops: [] });
		});

		it('shows Ready when the document has never been saved', async () => {
			const { updated_at: _ignored, ...neverSaved } = mockDoc;
			vi.mocked(get).mockResolvedValue(neverSaved);

			await ready();

			await waitFor(() => expect(status()).toBe('Ready'));
		});

		it('shows the load failure in the status bar and hides the toolbar', async () => {
			vi.mocked(get).mockRejectedValue(new Error('boom'));
			render(Page);

			await screen.findByTestId('error-state');

			expect(status()).toBe('Failed to load document');
			expect(screen.queryByTitle('評論')).toBeNull();
			expect(screen.queryByTitle('AI Writing Assistant')).toBeNull();
		});

		it('does not open a socket without an access token', async () => {
			vi.mocked(localStorage.removeItem)('access_token');

			render(Page);

			expect(await screen.findByText('Error saving document')).toBeInTheDocument();
			expect(globalThis.WebSocket).not.toHaveBeenCalled();
		});
	});

	describe('toolbar and side panels', () => {
		it('opens the comment panel and version history from the toolbar', async () => {
			await ready();

			await fireEvent.click(screen.getByTitle('評論'));
			await fireEvent.click(screen.getByTitle('版本歷史'));

			expect(harness.props.CommentPanel.isOpen).toBe(true);
			expect(harness.props.VersionHistoryPanel.isOpen).toBe(true);
		});

		it('passes identity and permissions to the comment panel', async () => {
			const { ws } = await ready();
			receive(ws, { type: 'connection_success', can_write: false, user_id: '7' });

			await waitFor(() => expect(harness.props.CommentPanel.canWrite).toBe(false));
			expect(harness.props.CommentPanel.currentUserId).toBe('7');
			expect(harness.props.CommentPanel.isOwner).toBe(true);
			expect(harness.props.CommentPanel.documentId).toBe('test-doc-123');
		});

		it('disables the AI writing assistant for read-only users', async () => {
			const { ws } = await ready();
			expect(screen.getByTitle('AI Writing Assistant')).not.toBeDisabled();

			receive(ws, { type: 'permission_update', can_write: false });

			await waitFor(() => expect(screen.getByTitle('AI Writing Assistant')).toBeDisabled());
		});

		it('tells version history how many other people are online', async () => {
			const { ws } = await ready();
			expect(harness.props.VersionHistoryPanel.onlineOthersCount).toBe(0);

			receive(ws, { type: 'connection_success', can_write: true, user_id: '1' });
			receive(ws, {
				type: 'presence_sync',
				users: [
					{ user_id: '1', username: 'me', color: '#111111' },
					{ user_id: '2', username: 'alice', color: '#222222' },
					{ user_id: '3', username: 'bob', color: '#333333' }
				]
			});

			await waitFor(() => expect(harness.props.VersionHistoryPanel.onlineOthersCount).toBe(2));
		});

		it('relays comment events to the comment panel', async () => {
			const { ws } = await ready();
			const comment = { id: 1, content: 'hi', parent_id: null };

			receive(ws, { type: 'comment_add', comment });
			receive(ws, { type: 'comment_update', comment_id: 1, content: 'edited', updated_at: 'T1' });
			receive(ws, { type: 'comment_delete', comment_id: 5, parent_id: 1 });
			receive(ws, { type: 'comment_delete', comment_id: 1 });

			expect(commentPanelExports.addCommentFromWS).toHaveBeenCalledWith(comment);
			expect(commentPanelExports.updateCommentFromWS).toHaveBeenCalledWith(1, 'edited', 'T1');
			expect(commentPanelExports.removeCommentFromWS).toHaveBeenNthCalledWith(1, 5, 1);
			// 沒帶 parent_id 的頂層評論以 null 表示
			expect(commentPanelExports.removeCommentFromWS).toHaveBeenNthCalledWith(2, 1, null);
		});
	});

	describe('connection lifecycle', () => {
		it('does not announce a restored connection on the first connect', async () => {
			const { ws } = await ready();

			receive(ws, { type: 'connection_success', can_write: true, user_id: '1' });

			expect(toastSuccess).not.toHaveBeenCalled();
		});

		it('treats 1001 (going away) as a normal close', async () => {
			const { ws } = await ready();
			vi.useFakeTimers();

			ws.onclose!({ code: 1001, reason: '' });
			await vi.advanceTimersByTimeAsync(60000);

			expect(globalThis.WebSocket).toHaveBeenCalledTimes(1);
			expect(toastError).not.toHaveBeenCalled();
		});

		it('treats 4000 as an application error with a default message and no reconnect', async () => {
			const { ws } = await ready();
			vi.useFakeTimers();

			ws.onclose!({ code: 4000, reason: '' });
			await vi.advanceTimersByTimeAsync(60000);

			expect(toastError).toHaveBeenCalledWith('Connection lost. Please refresh the page.');
			expect(globalThis.WebSocket).toHaveBeenCalledTimes(1);
			expect(status()).toBe('Error saving document');
		});

		it('flushes a throttled delta and cancels pending timers when leaving the page', async () => {
			const { ws, unmount } = await ready();
			vi.useFakeTimers();
			type('a'); // 立即送出
			type('b'); // 在節流窗口內，等待 trailing edge
			quill().onSelectionChange({ index: 1, length: 0 });

			unmount();

			expect(sent(ws)).toEqual([
				{ delta: { ops: [{ insert: 'a' }] } },
				{ delta: { ops: [{ insert: 'b' }] } }
			]);
			// 節流、游標與存檔計時器都已取消：之後不會再送出任何東西
			await vi.advanceTimersByTimeAsync(5000);
			expect(ws.send).toHaveBeenCalledTimes(2);
			expect(put).not.toHaveBeenCalled();
		});

		it('does not flush when the socket is no longer open', async () => {
			const { ws, unmount } = await ready();
			vi.useFakeTimers();
			type('a');
			ws.readyState = 3; // CLOSED
			type('b');

			unmount();

			expect(ws.send).toHaveBeenCalledTimes(1);
		});
	});

	describe('local edits', () => {
		it('sends the trailing delta for the rest of the throttle window only', async () => {
			const { ws } = await ready();
			vi.useFakeTimers();

			// 節流間隔 150ms：60ms 後的編輯只需再等剩下的 90ms
			type('a');
			await vi.advanceTimersByTimeAsync(60);
			type('b');
			await vi.advanceTimersByTimeAsync(89);
			expect(ws.send).toHaveBeenCalledTimes(1);
			await vi.advanceTimersByTimeAsync(1);
			expect(ws.send).toHaveBeenCalledTimes(2);

			// 距上次送出剛好一個節流間隔：立即送出
			await vi.advanceTimersByTimeAsync(150);
			type('c');
			expect(sent(ws).at(-1)).toEqual({ delta: { ops: [{ insert: 'c' }] } });
		});

		it('drops deltas typed while the socket is not open', async () => {
			const { ws } = await ready();
			vi.useFakeTimers();
			ws.readyState = 3; // CLOSED

			type('lost');
			await vi.advanceTimersByTimeAsync(200);
			ws.readyState = 1;
			type('next');

			expect(sent(ws)).toEqual([{ delta: { ops: [{ insert: 'next' }] } }]);
		});

		it('only sends content when it was edited since the last successful save', async () => {
			vi.mocked(put).mockResolvedValue({});
			await ready();
			const title = screen.getByPlaceholderText('Untitled Document');
			vi.useFakeTimers();

			await fireEvent.input(title, { target: { value: 'A' } });
			await vi.advanceTimersByTimeAsync(1500);
			type('!');
			await vi.advanceTimersByTimeAsync(1500);
			await fireEvent.input(title, { target: { value: 'B' } });
			await vi.advanceTimersByTimeAsync(1500);

			expect(vi.mocked(put).mock.calls.map(([, body]) => body)).toEqual([
				{ title: 'A' },
				{ title: 'A', content: { ops: [{ insert: 'Hello world\n' }] } },
				{ title: 'B' }
			]);
		});

		it('a failed title-only save does not start sending content', async () => {
			vi.mocked(put).mockRejectedValueOnce(new Error('offline')).mockResolvedValue({});
			await ready();
			const title = screen.getByPlaceholderText('Untitled Document');
			vi.useFakeTimers();

			await fireEvent.input(title, { target: { value: 'A' } });
			await vi.advanceTimersByTimeAsync(1500);
			await fireEvent.input(title, { target: { value: 'B' } });
			await vi.advanceTimersByTimeAsync(1500);

			expect(put).toHaveBeenLastCalledWith('/documents/test-doc-123/', { title: 'B' });
		});

		it('demotion to read-only discards unsent edits and the pending save', async () => {
			vi.mocked(put).mockResolvedValue({});
			const { ws } = await ready();
			vi.useFakeTimers();
			type('a');
			type('b');

			receive(ws, { type: 'permission_update', can_write: false });
			await vi.advanceTimersByTimeAsync(2000);

			expect(sent(ws)).toEqual([{ delta: { ops: [{ insert: 'a' }] } }]);
			expect(put).not.toHaveBeenCalled();
			expect(status()).toBe(lastSaveAt(mockDoc.updated_at));

			// 再次升權後只改標題：先前被丟棄的內容編輯不應被當成未存檔內容送出
			receive(ws, { type: 'permission_update', can_write: true });
			await fireEvent.input(screen.getByPlaceholderText('Untitled Document'), {
				target: { value: 'Renamed' }
			});
			await vi.advanceTimersByTimeAsync(1500);
			expect(put).toHaveBeenCalledWith('/documents/test-doc-123/', { title: 'Renamed' });
		});

		it('a restore from another user discards unsent edits, then settles to idle', async () => {
			vi.mocked(put).mockResolvedValue({});
			const { ws } = await ready();
			vi.useFakeTimers();
			type('a');
			type('b');

			receive(ws, {
				type: 'doc_restored',
				content: { ops: [{ insert: 'old\n' }] },
				updated_at: '2026-03-08T09:30:00Z',
				restored_by: '2',
				restored_by_username: 'alice',
				restored_to_version: 1
			});
			await vi.advanceTimersByTimeAsync(1999);
			expect(status()).toBe('All changes saved');
			await vi.advanceTimersByTimeAsync(1);
			expect(status()).toBe(lastSaveAt('2026-03-08T09:30:00Z'));
			expect(sent(ws)).toEqual([{ delta: { ops: [{ insert: 'a' }] } }]);
			expect(put).not.toHaveBeenCalled();

			await fireEvent.input(screen.getByPlaceholderText('Untitled Document'), {
				target: { value: 'Renamed' }
			});
			await vi.advanceTimersByTimeAsync(1500);
			expect(put).toHaveBeenCalledWith('/documents/test-doc-123/', { title: 'Renamed' });
		});

		it('does not hide new unsaved changes when the restore notice times out', async () => {
			vi.mocked(put).mockImplementation(() => new Promise(() => {}));
			const { ws } = await ready();
			vi.useFakeTimers();

			receive(ws, {
				type: 'doc_restored',
				content: { ops: [{ insert: 'old\n' }] },
				updated_at: '2026-03-08T09:30:00Z',
				restored_by: '2',
				restored_by_username: 'alice',
				restored_to_version: 1
			});
			await vi.advanceTimersByTimeAsync(1000);
			await fireEvent.input(screen.getByPlaceholderText('Untitled Document'), {
				target: { value: 'Renamed' }
			});
			await vi.advanceTimersByTimeAsync(1001);

			expect(status()).toBe('Unsaved changes');
		});
	});

	describe('cursor sharing', () => {
		it('does not send cursors while the socket is not open', async () => {
			const { ws } = await ready();
			vi.useFakeTimers();

			ws.readyState = 3;
			quill().onSelectionChange({ index: 1, length: 0 });
			await vi.advanceTimersByTimeAsync(500);

			expect(ws.send).not.toHaveBeenCalled();
		});

		it('drops a throttled cursor when the socket closes before it is sent', async () => {
			const { ws } = await ready();
			vi.useFakeTimers();

			quill().onSelectionChange({ index: 1, length: 0 });
			ws.readyState = 3;
			await vi.advanceTimersByTimeAsync(500);

			expect(ws.send).not.toHaveBeenCalled();
		});

		it('starts a new throttle window after each send', async () => {
			const { ws } = await ready();
			vi.useFakeTimers();

			quill().onSelectionChange({ index: 1, length: 0 });
			await vi.advanceTimersByTimeAsync(100);
			quill().onSelectionChange({ index: 2, length: 0 });
			await vi.advanceTimersByTimeAsync(50);
			expect(sent(ws)).toEqual([{ type: 'cursor_move', index: 2, length: 0 }]);

			quill().onSelectionChange({ index: 3, length: 0 });
			await vi.advanceTimersByTimeAsync(149);
			expect(ws.send).toHaveBeenCalledTimes(1);
			await vi.advanceTimersByTimeAsync(1);
			expect(sent(ws).at(-1)).toEqual({ type: 'cursor_move', index: 3, length: 0 });
		});
	});

	describe('AI streams', () => {
		function aiDialog() {
			return harness.props.AIDialog as {
				onStream: (action: string, text: string) => boolean;
				onApply: (text: string) => void;
				onCancelStream: () => void;
				streaming: boolean;
				streamText: string;
			};
		}

		function askDialog() {
			return harness.props.AIAskDialog as {
				isOpen: boolean;
				onAsk: (q: string, t: string) => boolean;
				streaming: boolean;
				streamText: string;
			};
		}

		it('requires a non-empty selection for the writing assistant', async () => {
			editor.selection = { index: 3, length: 0 };
			await ready();

			await fireEvent.click(screen.getByTitle('AI Writing Assistant'));

			expect(toastWarning).toHaveBeenCalledWith('Please select text first');
			expect(harness.props.AIDialog.isOpen).toBe(false);
		});

		it('ignores an apply without a saved selection', async () => {
			await ready();

			aiDialog().onApply('new text');

			expect(editor.deleteText).not.toHaveBeenCalled();
			expect(editor.insertText).not.toHaveBeenCalled();
		});

		it('a normal stream end is not reported as an error', async () => {
			const { ws } = await ready();
			aiDialog().onStream('summarize', 'abc');

			receive(ws, { type: 'ai_stream_end', action: 'summarize' });

			await waitFor(() => expect(aiDialog().streaming).toBe(false));
			expect(toastError).not.toHaveBeenCalled();
		});

		it('a stream error stops streaming', async () => {
			const { ws } = await ready();
			aiDialog().onStream('summarize', 'abc');
			await waitFor(() => expect(aiDialog().streaming).toBe(true));

			receive(ws, { type: 'ai_stream_error', message: 'boom' });

			await waitFor(() => expect(aiDialog().streaming).toBe(false));
		});

		it('ignores chunks without text', async () => {
			const { ws } = await ready();
			aiDialog().onStream('summarize', 'abc');

			receive(ws, { type: 'ai_stream_chunk', chunk: '摘' });
			receive(ws, { type: 'ai_stream_chunk' });

			await waitFor(() => expect(aiDialog().streamText).toBe('摘'));
		});

		it('cancelling with a closed socket only stops the local stream', async () => {
			const { ws } = await ready();
			aiDialog().onStream('summarize', 'abc');
			ws.readyState = 3;

			aiDialog().onCancelStream();

			expect(sent(ws)).toEqual([{ type: 'ai_stream', action: 'summarize', text: 'abc' }]);
			await waitFor(() => expect(aiDialog().streaming).toBe(false));
		});

		it('asking marks the stream as running and clears previous output', async () => {
			const { ws } = await ready();
			aiDialog().onStream('polish', 'abc');
			receive(ws, { type: 'ai_stream_chunk', chunk: '舊' });
			receive(ws, { type: 'ai_stream_end' });
			await waitFor(() => expect(askDialog().streamText).toBe('舊'));

			expect(askDialog().onAsk('重點？', '全文')).toBe(true);

			await waitFor(() => expect(askDialog().streaming).toBe(true));
			expect(askDialog().streamText).toBe('');
		});

		it('refuses to ask when the socket is not open', async () => {
			const { ws } = await ready();
			ws.readyState = 3;

			expect(askDialog().onAsk('重點？', '全文')).toBe(false);

			expect(toastError).toHaveBeenCalledWith('連線中斷，無法使用 AI 串流');
			expect(ws.send).not.toHaveBeenCalled();
			expect(askDialog().streaming).toBe(false);
		});

		it('opening document Q&A resets output left over from another stream', async () => {
			const { ws } = await ready();
			aiDialog().onStream('polish', 'abc');
			receive(ws, { type: 'ai_stream_chunk', chunk: '殘留' });
			await waitFor(() => expect(askDialog().streamText).toBe('殘留'));

			await fireEvent.click(screen.getByTitle('文件問答'));

			expect(askDialog().isOpen).toBe(true);
			expect(askDialog().streamText).toBe('');
			expect(askDialog().streaming).toBe(false);
		});
	});

	describe('version restore reload', () => {
		function restore() {
			return (harness.props.VersionHistoryPanel as { onRestore: () => Promise<void> }).onRestore();
		}

		it('returns to idle two seconds after reloading', async () => {
			await ready();
			vi.mocked(get).mockResolvedValue({ ...mockDoc, updated_at: '2026-03-09T09:00:00Z' });
			vi.useFakeTimers();

			await restore();
			await vi.advanceTimersByTimeAsync(1999);
			expect(status()).toBe('All changes saved');
			await vi.advanceTimersByTimeAsync(1);

			expect(status()).toBe(lastSaveAt('2026-03-09T09:00:00Z'));
		});

		it('keeps new unsaved changes visible after the restore notice times out', async () => {
			vi.mocked(put).mockImplementation(() => new Promise(() => {}));
			await ready();
			vi.useFakeTimers();

			await restore();
			await vi.advanceTimersByTimeAsync(1000);
			await fireEvent.input(screen.getByPlaceholderText('Untitled Document'), {
				target: { value: 'Renamed' }
			});
			await vi.advanceTimersByTimeAsync(1001);

			expect(status()).toBe('Unsaved changes');
		});

		it('reports a failed reload', async () => {
			await ready();
			vi.mocked(get).mockRejectedValue(new Error('offline'));

			await restore();

			expect(toastError).toHaveBeenCalledWith('Failed to reload document.');
			expect(editor.setContents).not.toHaveBeenCalled();
		});

		it('falls back to an empty document when the reloaded version has no content', async () => {
			await ready();
			const { content: _ignored, ...withoutContent } = mockDoc;
			vi.mocked(get).mockResolvedValue(withoutContent);

			await restore();

			expect(editor.setContents).toHaveBeenCalledWith([], 'silent');
		});
	});
});

describe('Document Page - share modal details', () => {
	const alice = { id: 2, username: 'alice', email: 'alice@example.com', permission: 'read' };
	const bob = { id: 3, username: 'bob', email: 'bob@example.com', permission: 'write' };

	beforeEach(() => {
		vi.clearAllMocks();
		setupBrowserMocks();
		harness.editor = null;
		vi.mocked(get).mockImplementation((url: string) =>
			Promise.resolve(url.includes('/collaborators/') ? [{ ...alice }, { ...bob }] : mockDoc)
		);
	});

	async function openShare() {
		render(Page);
		await fireEvent.click(await screen.findByTitle('Share'));
		await screen.findByLabelText('Change permission for alice');
	}

	function permissionOf(name: string) {
		return (screen.getByLabelText(`Change permission for ${name}`) as HTMLSelectElement).value;
	}

	it('reports when collaborators cannot be loaded', async () => {
		vi.mocked(get).mockImplementation((url: string) =>
			url.includes('/collaborators/') ? Promise.reject(new Error('boom')) : Promise.resolve(mockDoc)
		);
		render(Page);

		await fireEvent.click(await screen.findByTitle('Share'));

		await waitFor(() => expect(toastError).toHaveBeenCalledWith('Could not load collaborators.'));
	});

	it('updates only the changed collaborator', async () => {
		vi.mocked(put).mockResolvedValue({ ...alice, permission: 'write' });
		await openShare();

		await fireEvent.change(screen.getByLabelText('Change permission for alice'), {
			target: { value: 'write' }
		});

		await waitFor(() =>
			expect(toastSuccess).toHaveBeenCalledWith('alice can now edit this document.')
		);
		expect(permissionOf('alice')).toBe('write');
		expect(permissionOf('bob')).toBe('write');
		expect(screen.getAllByText('bob')).toHaveLength(1);
	});

	it('removes only the confirmed collaborator', async () => {
		vi.mocked(del).mockResolvedValue(null);
		await openShare();

		await fireEvent.click(screen.getAllByTitle('Remove collaborator')[1]);
		await fireEvent.click(screen.getByText('Remove'));

		await waitFor(() => expect(screen.queryByLabelText('Change permission for bob')).toBeNull());
		expect(del).toHaveBeenCalledWith('/documents/test-doc-123/collaborators/3/');
		expect(screen.getByLabelText('Change permission for alice')).toBeInTheDocument();
	});

	it.each([['Cancel'], ['Close']])(
		'dismissing the removal confirmation with %s keeps the collaborator',
		async (button) => {
			await openShare();
			await fireEvent.click(screen.getAllByTitle('Remove collaborator')[0]);
			const dialog = screen
				.getByText('Remove Collaborator')
				.closest('.modal-content') as HTMLElement;

			await fireEvent.click(within(dialog).getByRole('button', { name: button }));

			expect(screen.queryByText('Remove Collaborator')).toBeNull();
			expect(del).not.toHaveBeenCalled();
			expect(screen.getByLabelText('Change permission for alice')).toBeInTheDocument();
		}
	);

	it('shows a generic message when adding fails without an Error', async () => {
		vi.mocked(post).mockRejectedValue('nope');
		await openShare();

		await fireEvent.input(screen.getByPlaceholderText('Enter username'), {
			target: { value: 'carol' }
		});
		await fireEvent.click(screen.getByText('Add'));

		await waitFor(() => expect(toastError).toHaveBeenCalledWith('Failed to add collaborator.'));
	});

	it.each([['Done'], ['Close']])('closes the share modal with %s', async (button) => {
		await openShare();
		const modal = screen
			.getByText('Share "Test Document"')
			.closest('.modal-content') as HTMLElement;

		await fireEvent.click(within(modal).getAllByRole('button', { name: button })[0]);

		expect(screen.queryByText('Share "Test Document"')).toBeNull();
	});
});
