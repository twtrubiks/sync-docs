import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import VersionHistoryPanel from './VersionHistoryPanel.svelte';

// Mock API 模組
vi.mock('$lib/api/versions', () => ({
	getVersions: vi.fn(),
	getVersionDetail: vi.fn(),
	restoreVersion: vi.fn()
}));

// Mock toast
vi.mock('$lib/toast', () => ({
	toastSuccess: vi.fn(),
	toastError: vi.fn(),
	toastWarning: vi.fn()
}));

// Mock $app/environment
vi.mock('$app/environment', () => ({
	browser: true
}));

// Mock Quill：jsdom 無法初始化真正的 Quill（Invalid Quill container），
// 不 mock 的話每次預覽都會走錯誤路徑，預覽渲染邏輯等於沒被測到
const quillMock = vi.hoisted(() => ({
	instances: [] as { options: unknown; setContents: ReturnType<typeof vi.fn> }[]
}));
vi.mock('quill', () => ({
	default: class MockQuill {
		options: unknown;
		setContents = vi.fn();
		constructor(_container: HTMLElement, options: unknown) {
			this.options = options;
			quillMock.instances.push(this);
		}
	}
}));

import { getVersions, getVersionDetail, restoreVersion } from '$lib/api/versions';
import { toastSuccess, toastError } from '$lib/toast';

const mockVersionItems = [
	{
		id: 'version-1',
		version_number: 2,
		created_at: '2024-01-15T10:30:00Z',
		created_by_username: 'testuser'
	},
	{
		id: 'version-2',
		version_number: 1,
		created_at: '2024-01-15T09:00:00Z',
		created_by_username: 'testuser'
	}
];

const mockPaginatedResponse = {
	items: mockVersionItems,
	total: 2,
	page: 1,
	page_size: 20,
	total_pages: 1
};

describe('VersionHistoryPanel', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		vi.mocked(getVersions).mockResolvedValue(mockPaginatedResponse);
	});

	it('should load versions when opened', async () => {
		render(VersionHistoryPanel, {
			props: {
				documentId: 'doc-123',
				isOpen: true
			}
		});

		await waitFor(() => {
			expect(getVersions).toHaveBeenCalledWith('doc-123', 1);
		});

		expect(screen.getByText('版本 2')).toBeInTheDocument();
		expect(screen.getByText('版本 1')).toBeInTheDocument();
	});

	it('should not load versions when closed', () => {
		render(VersionHistoryPanel, {
			props: {
				documentId: 'doc-123',
				isOpen: false
			}
		});

		expect(getVersions).not.toHaveBeenCalled();
	});

	it('should show empty state message', async () => {
		vi.mocked(getVersions).mockResolvedValue({
			items: [],
			total: 0,
			page: 1,
			page_size: 20,
			total_pages: 1
		});

		render(VersionHistoryPanel, {
			props: {
				documentId: 'doc-123',
				isOpen: true
			}
		});

		await waitFor(() => {
			expect(screen.getByText('尚無版本記錄')).toBeInTheDocument();
		});
	});

	it('should load version detail when clicked', async () => {
		vi.mocked(getVersionDetail).mockResolvedValue({
			...mockVersionItems[0],
			content: { ops: [{ insert: 'test' }] }
		});

		render(VersionHistoryPanel, {
			props: {
				documentId: 'doc-123',
				isOpen: true
			}
		});

		await waitFor(() => {
			expect(screen.getByText('版本 2')).toBeInTheDocument();
		});

		await fireEvent.click(screen.getByText('版本 2'));

		expect(getVersionDetail).toHaveBeenCalledWith('doc-123', 'version-1');
	});

	it('should show restore button when version is selected', async () => {
		vi.mocked(getVersionDetail).mockResolvedValue({
			...mockVersionItems[0],
			content: { ops: [{ insert: 'test' }] }
		});

		render(VersionHistoryPanel, {
			props: {
				documentId: 'doc-123',
				isOpen: true
			}
		});

		await waitFor(() => {
			expect(screen.getByText('版本 2')).toBeInTheDocument();
		});

		await fireEvent.click(screen.getByText('版本 2'));

		await waitFor(() => {
			expect(screen.getByText('還原到版本 2')).toBeInTheDocument();
		});
	});

	it('should call restore API and callback when restored', async () => {
		const onRestore = vi.fn();
		vi.mocked(getVersionDetail).mockResolvedValue({
			...mockVersionItems[0],
			content: { ops: [{ insert: 'test' }] }
		});
		vi.mocked(restoreVersion).mockResolvedValue({
			success: true,
			message: '已還原到版本 2',
			new_version_number: 3
		});

		render(VersionHistoryPanel, {
			props: {
				documentId: 'doc-123',
				isOpen: true,
				onRestore
			}
		});

		await waitFor(() => {
			expect(screen.getByText('版本 2')).toBeInTheDocument();
		});

		await fireEvent.click(screen.getByText('版本 2'));

		await waitFor(() => {
			expect(screen.getByText('還原到版本 2')).toBeInTheDocument();
		});

		// 點擊還原按鈕 → 開啟 ConfirmDialog
		await fireEvent.click(screen.getByText('還原到版本 2'));

		// 等待 ConfirmDialog 出現，點擊確認按鈕
		await waitFor(() => {
			expect(screen.getByText('還原')).toBeInTheDocument();
		});
		await fireEvent.click(screen.getByText('還原'));

		await waitFor(() => {
			expect(restoreVersion).toHaveBeenCalledWith('doc-123', 'version-1');
			expect(onRestore).toHaveBeenCalled();
		});
	});

	it('should warn about online collaborators in restore confirmation', async () => {
		vi.mocked(getVersionDetail).mockResolvedValue({
			...mockVersionItems[0],
			content: { ops: [{ insert: 'test' }] }
		});

		render(VersionHistoryPanel, {
			props: {
				documentId: 'doc-123',
				isOpen: true,
				onlineOthersCount: 2
			}
		});

		await waitFor(() => {
			expect(screen.getByText('版本 2')).toBeInTheDocument();
		});

		await fireEvent.click(screen.getByText('版本 2'));

		await waitFor(() => {
			expect(screen.getByText('還原到版本 2')).toBeInTheDocument();
		});

		// 點擊還原按鈕 → 開啟 ConfirmDialog，確認訊息包含線上協作者警告
		await fireEvent.click(screen.getByText('還原到版本 2'));

		await waitFor(() => {
			expect(screen.getByText(/目前有 2 位其他協作者在線上/)).toBeInTheDocument();
		});
	});

	it('should display created_by_username', async () => {
		render(VersionHistoryPanel, {
			props: {
				documentId: 'doc-123',
				isOpen: true
			}
		});

		await waitFor(() => {
			// 因為有多個版本都是同一用戶創建，所以用 getAllByText
			const elements = screen.getAllByText('testuser');
			expect(elements.length).toBe(2);
		});
	});

	it('should show panel title', async () => {
		render(VersionHistoryPanel, {
			props: {
				documentId: 'doc-123',
				isOpen: true
			}
		});

		expect(screen.getByText('版本歷史')).toBeInTheDocument();
	});
	// ── 變異測試補強 ──

	async function openAndSelect(props: Record<string, unknown> = {}) {
		vi.mocked(getVersionDetail).mockResolvedValue({
			...mockVersionItems[0],
			content: { ops: [{ insert: 'test' }] }
		});
		render(VersionHistoryPanel, { props: { documentId: 'doc-123', isOpen: true, ...props } });
		await screen.findByText('版本 2');
		await fireEvent.click(screen.getByText('版本 2'));
		await screen.findByText('還原到版本 2');
	}

	it('offers load more only while pages remain, and appends them', async () => {
		vi.mocked(getVersions)
			.mockResolvedValueOnce({ ...mockPaginatedResponse, page: 1, total_pages: 2 })
			.mockResolvedValueOnce({
				items: [
					{
						id: 'version-0',
						version_number: 0,
						created_at: '2024-01-15T08:00:00Z',
						created_by_username: 'testuser'
					}
				],
				total: 3,
				page: 2,
				page_size: 20,
				total_pages: 2
			});
		render(VersionHistoryPanel, { props: { documentId: 'doc-123', isOpen: true } });

		await fireEvent.click(await screen.findByText('載入更多版本'));

		expect(await screen.findByText('版本 0')).toBeInTheDocument();
		expect(getVersions).toHaveBeenLastCalledWith('doc-123', 2);
		expect(screen.getByText('版本 2')).toBeInTheDocument();
		expect(screen.queryByText('載入更多版本')).toBeNull();
	});

	it('hides load more on the last page', async () => {
		render(VersionHistoryPanel, { props: { documentId: 'doc-123', isOpen: true } });

		await screen.findByText('版本 2');

		expect(screen.queryByText('載入更多版本')).toBeNull();
	});

	it('reports version list failures', async () => {
		vi.mocked(getVersions).mockRejectedValue(new Error('boom'));

		render(VersionHistoryPanel, { props: { documentId: 'doc-123', isOpen: true } });

		await waitFor(() => expect(toastError).toHaveBeenCalledWith('載入版本失敗'));
	});

	it('renders previews in a single read-only Quill without toolbar', async () => {
		quillMock.instances.length = 0;
		vi.mocked(getVersionDetail)
			.mockResolvedValueOnce({ ...mockVersionItems[0], content: { ops: [{ insert: 'v2\n' }] } })
			.mockResolvedValueOnce({ ...mockVersionItems[1], content: { ops: [{ insert: 'v1\n' }] } });
		render(VersionHistoryPanel, { props: { documentId: 'doc-123', isOpen: true } });

		await fireEvent.click(await screen.findByText('版本 2'));
		await waitFor(() => expect(quillMock.instances).toHaveLength(1));
		const [quill] = quillMock.instances;
		expect(quill.options).toEqual({ theme: 'snow', readOnly: true, modules: { toolbar: false } });
		await waitFor(() =>
			expect(quill.setContents).toHaveBeenCalledWith([{ insert: 'v2\n' }], 'silent')
		);

		await fireEvent.click(screen.getByText('版本 1'));
		await waitFor(() =>
			expect(quill.setContents).toHaveBeenCalledWith([{ insert: 'v1\n' }], 'silent')
		);
		expect(quillMock.instances).toHaveLength(1); // 重複使用同一個實例
		expect(toastError).not.toHaveBeenCalled();
	});

	it('does not refetch when the selected version is clicked again', async () => {
		await openAndSelect();

		await fireEvent.click(screen.getByText('版本 2'));

		expect(getVersionDetail).toHaveBeenCalledTimes(1);
	});

	it('reports preview failures', async () => {
		vi.mocked(getVersionDetail).mockRejectedValue(new Error('boom'));
		render(VersionHistoryPanel, { props: { documentId: 'doc-123', isOpen: true } });

		await fireEvent.click(await screen.findByText('版本 2'));

		await waitFor(() => expect(toastError).toHaveBeenCalledWith('載入版本內容失敗'));
	});

	it('shows the server message, closes and notifies after restoring', async () => {
		const onRestore = vi.fn();
		vi.mocked(restoreVersion).mockResolvedValue({
			success: true,
			message: '已還原到版本 2',
			new_version_number: 3
		});
		await openAndSelect({ onRestore });

		await fireEvent.click(screen.getByText('還原到版本 2'));
		expect(screen.getByText(/確定要還原到版本 2？這將覆蓋目前的內容。$/)).toBeInTheDocument();
		await fireEvent.click(screen.getByText('還原'));

		await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('已還原到版本 2'));
		expect(onRestore).toHaveBeenCalledTimes(1);
		expect(screen.queryByText('版本歷史')).toBeNull();
	});

	it('keeps the panel open when restoring fails', async () => {
		const onRestore = vi.fn();
		vi.mocked(restoreVersion).mockRejectedValue(new Error('boom'));
		await openAndSelect({ onRestore });

		await fireEvent.click(screen.getByText('還原到版本 2'));
		await fireEvent.click(screen.getByText('還原'));

		await waitFor(() => expect(toastError).toHaveBeenCalledWith('還原失敗'));
		expect(onRestore).not.toHaveBeenCalled();
		expect(screen.getByText('版本歷史')).toBeInTheDocument();
		expect(screen.getByText('還原到版本 2').closest('button')).not.toBeDisabled();
	});

	function deferred<T>() {
		let resolve!: (value: T) => void;
		let reject!: (reason: unknown) => void;
		const promise = new Promise<T>((res, rej) => {
			resolve = res;
			reject = rej;
		});
		return { promise, resolve, reject };
	}

	const olderPage = (page: number, total_pages: number) => ({
		items: [
			{
				id: `version-old-${page}`,
				version_number: -page,
				created_at: '2024-01-15T08:00:00Z',
				created_by_username: 'testuser'
			}
		],
		total: 3,
		page,
		page_size: 20,
		total_pages
	});

	describe('closing', () => {
		it.each([
			['the close button', () => fireEvent.click(screen.getByLabelText('關閉'))],
			['the backdrop', () => fireEvent.click(screen.getByLabelText('關閉版本歷史'))],
			[
				'Escape on the backdrop',
				() => fireEvent.keyDown(screen.getByLabelText('關閉版本歷史'), { key: 'Escape' })
			]
		])('closes with %s', async (_label, close) => {
			render(VersionHistoryPanel, { props: { documentId: 'doc-123', isOpen: true } });
			await screen.findByText('版本 2');

			await close();

			expect(screen.queryByText('版本歷史')).toBeNull();
		});

		it('ignores other keys on the backdrop', async () => {
			render(VersionHistoryPanel, { props: { documentId: 'doc-123', isOpen: true } });

			await fireEvent.keyDown(screen.getByLabelText('關閉版本歷史'), { key: 'Enter' });

			expect(screen.getByText('版本歷史')).toBeInTheDocument();
		});
	});

	it('shows a loading state until versions arrive', async () => {
		vi.mocked(getVersions).mockReturnValue(new Promise(() => {}));

		render(VersionHistoryPanel, { props: { documentId: 'doc-123', isOpen: true } });

		expect(await screen.findByText('載入中...')).toBeInTheDocument();
		expect(screen.queryByText('尚無版本記錄')).toBeNull();
	});

	describe('loading more', () => {
		it('disables the button while loading and loads each page once', async () => {
			const next = deferred<ReturnType<typeof olderPage>>();
			vi.mocked(getVersions)
				.mockResolvedValueOnce({ ...mockPaginatedResponse, page: 1, total_pages: 3 })
				.mockReturnValueOnce(next.promise)
				.mockResolvedValueOnce(olderPage(3, 3));
			render(VersionHistoryPanel, { props: { documentId: 'doc-123', isOpen: true } });
			const loadMore = (await screen.findByText('載入更多版本')).closest('button')!;

			await fireEvent.click(loadMore);
			expect(loadMore).toBeDisabled();
			expect(loadMore).toHaveTextContent('載入中...');
			await fireEvent.click(loadMore); // 載入中再點一次不應重複請求同一頁
			expect(getVersions).toHaveBeenCalledTimes(2);

			next.resolve(olderPage(2, 3));
			expect(await screen.findByText('版本 -2')).toBeInTheDocument();
			expect(screen.getByText('載入更多版本').closest('button')).not.toBeDisabled();

			await fireEvent.click(screen.getByText('載入更多版本'));
			expect(await screen.findByText('版本 -3')).toBeInTheDocument();
			expect(getVersions).toHaveBeenLastCalledWith('doc-123', 3);
		});

		it('reports failures and lets the user retry', async () => {
			vi.mocked(getVersions)
				.mockResolvedValueOnce({ ...mockPaginatedResponse, page: 1, total_pages: 2 })
				.mockRejectedValueOnce(new Error('boom'));
			render(VersionHistoryPanel, { props: { documentId: 'doc-123', isOpen: true } });

			await fireEvent.click(await screen.findByText('載入更多版本'));

			await waitFor(() => expect(toastError).toHaveBeenCalledWith('載入更多版本失敗'));
			expect(screen.getByText('載入更多版本').closest('button')).not.toBeDisabled();
		});
	});

	describe('previews', () => {
		it('shows a loading state, then the unavailable message when loading fails', async () => {
			const detail = deferred<never>();
			vi.mocked(getVersionDetail).mockReturnValue(detail.promise);
			render(VersionHistoryPanel, { props: { documentId: 'doc-123', isOpen: true } });

			await fireEvent.click(await screen.findByText('版本 2'));
			expect(screen.getByText('版本 2 預覽')).toBeInTheDocument();
			expect(screen.getByText('載入中...')).toBeInTheDocument();
			expect(screen.queryByText('無法載入內容')).toBeNull();

			detail.reject(new Error('boom'));
			expect(await screen.findByText('無法載入內容')).toBeInTheDocument();
			expect(screen.queryByText('載入中...')).toBeNull();
		});

		it('does not show the unavailable message once content is loaded', async () => {
			await openAndSelect();

			await waitFor(() => expect(screen.queryByText('載入中...')).toBeNull());
			expect(screen.queryByText('無法載入內容')).toBeNull();
		});

		it('skips rendering content without ops', async () => {
			quillMock.instances.length = 0;
			vi.mocked(getVersionDetail).mockResolvedValue({
				...mockVersionItems[0],
				content: {}
			});
			render(VersionHistoryPanel, { props: { documentId: 'doc-123', isOpen: true } });

			await fireEvent.click(await screen.findByText('版本 2'));

			await waitFor(() => expect(quillMock.instances).toHaveLength(1));
			expect(quillMock.instances[0].setContents).not.toHaveBeenCalled();
		});

		it('highlights only the selected version', async () => {
			await openAndSelect();

			const selected = screen.getByText('版本 2').closest('button')!;
			const other = screen.getByText('版本 1').closest('button')!;
			expect(selected).toHaveClass('border-primary-500');
			expect(other).not.toHaveClass('border-primary-500');
			expect(other).toHaveClass('border-transparent');
		});

		it('formats version times in zh-TW', async () => {
			render(VersionHistoryPanel, { props: { documentId: 'doc-123', isOpen: true } });

			const expected = new Date('2024-01-15T10:30:00Z').toLocaleString('zh-TW', {
				month: 'short',
				day: 'numeric',
				hour: '2-digit',
				minute: '2-digit'
			});
			expect(await screen.findByText(expected)).toBeInTheDocument();
		});
	});

	it('disables restoring while a restore is in progress and restores only once', async () => {
		const restore = deferred<{ success: boolean; message: string; new_version_number: number }>();
		vi.mocked(restoreVersion).mockReturnValue(restore.promise);
		await openAndSelect();

		await fireEvent.click(screen.getByText('還原到版本 2'));
		await fireEvent.click(screen.getByText('還原'));

		const button = screen.getByText('還原中...').closest('button')!;
		expect(button).toBeDisabled();
		await fireEvent.click(button);
		expect(screen.queryByRole('alertdialog')).toBeNull();
		expect(restoreVersion).toHaveBeenCalledTimes(1);

		restore.resolve({ success: true, message: 'ok', new_version_number: 3 });
		await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('ok'));
	});
});
