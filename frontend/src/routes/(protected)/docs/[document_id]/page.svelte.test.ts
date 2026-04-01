import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';

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

// Mock child Svelte components to avoid rendering issues in jsdom
// Svelte 5 components are functions; return a no-op function as default export
function createMockComponent() {
	// Svelte 5 compiled component signature
	return function MockComponent() {};
}

vi.mock('$lib/components/QuillEditor.svelte', () => ({
	default: createMockComponent()
}));

vi.mock('$lib/components/VersionHistoryPanel.svelte', () => ({
	default: createMockComponent()
}));

vi.mock('$lib/components/AIDialog.svelte', () => ({
	default: createMockComponent()
}));

vi.mock('$lib/components/CommentPanel.svelte', () => ({
	default: createMockComponent()
}));

// Import after mocks
import Page from './+page.svelte';
import { get } from '$lib/auth';
import { toastError } from '$lib/toast';

// Mock document data
const mockDoc = {
	title: 'Test Document',
	content: { ops: [{ insert: 'Hello\n' }] },
	is_owner: true,
	can_write: true,
	updated_at: '2026-03-07T12:00:00Z'
};

describe('Document Page - Load States', () => {
	beforeEach(() => {
		vi.clearAllMocks();

		// Mock WebSocket
		globalThis.WebSocket = vi.fn().mockImplementation(() => ({
			close: vi.fn(),
			send: vi.fn(),
			readyState: 1,
			onopen: null,
			onclose: null,
			onmessage: null,
			onerror: null
		})) as unknown as typeof WebSocket;

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
		vi.mocked(get)
			.mockRejectedValueOnce(new Error('Network error'))
			.mockResolvedValueOnce(mockDoc);

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
		vi.mocked(get)
			.mockRejectedValueOnce(new Error('Network error'))
			.mockResolvedValueOnce(mockDoc);

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
