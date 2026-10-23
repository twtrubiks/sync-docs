import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, waitFor } from '@testing-library/svelte';
import AIMetadataDialog from './AIMetadataDialog.svelte';

// Mock AI API
vi.mock('$lib/ai', () => ({
	metadataWithAI: vi.fn()
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

import { metadataWithAI } from '$lib/ai';
import { toastError } from '$lib/toast';

describe('AIMetadataDialog', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('should not render when isOpen is false', () => {
		render(AIMetadataDialog, {
			props: { isOpen: false, documentText: '文件內容' }
		});
		expect(screen.queryByText('文件分析')).toBeNull();
	});

	it('should auto-analyze on open and call metadataWithAI with document text', async () => {
		vi.mocked(metadataWithAI).mockResolvedValue({
			success: true,
			result: { summary: '摘要', tags: ['標籤'], language: 'zh-Hant', reading_time: 3 }
		});

		render(AIMetadataDialog, {
			props: { isOpen: true, documentText: '這是文件內容' }
		});

		await waitFor(() => {
			expect(metadataWithAI).toHaveBeenCalledWith('這是文件內容');
		});
	});

	it('should render metadata fields when API succeeds', async () => {
		vi.mocked(metadataWithAI).mockResolvedValue({
			success: true,
			result: {
				summary: '這是一份 Docker 教學',
				tags: ['Docker', '容器化'],
				language: 'zh-Hant',
				reading_time: 5
			}
		});

		render(AIMetadataDialog, {
			props: { isOpen: true, documentText: 'Docker 教學內容' }
		});

		await waitFor(() => {
			expect(screen.getByText('這是一份 Docker 教學')).toBeInTheDocument();
			expect(screen.getByText('Docker')).toBeInTheDocument();
			expect(screen.getByText('容器化')).toBeInTheDocument();
			expect(screen.getByText('zh-Hant')).toBeInTheDocument();
			expect(screen.getByText('5 分鐘')).toBeInTheDocument();
		});
	});

	it('should show error toast when API fails', async () => {
		vi.mocked(metadataWithAI).mockResolvedValue({
			success: false,
			error: 'Metadata error'
		});

		render(AIMetadataDialog, {
			props: { isOpen: true, documentText: '文件內容' }
		});

		await waitFor(() => {
			expect(toastError).toHaveBeenCalledWith('Metadata error');
		});
	});
	// ── 變異測試補強 ──

	it('does not analyze an empty document', async () => {
		render(AIMetadataDialog, { props: { isOpen: true, documentText: '   ' } });

		await Promise.resolve();
		expect(metadataWithAI).not.toHaveBeenCalled();
	});

	it('analyzes once per document content, even when reopened', async () => {
		vi.mocked(metadataWithAI).mockResolvedValue({
			success: true,
			result: { summary: '摘要', tags: [], language: 'zh-Hant', reading_time: 1 }
		});
		const { rerender } = render(AIMetadataDialog, {
			props: { isOpen: true, documentText: '內容 A' }
		});
		await waitFor(() => expect(metadataWithAI).toHaveBeenCalledTimes(1));

		await rerender({ isOpen: false, documentText: '內容 A' });
		await rerender({ isOpen: true, documentText: '內容 A' });
		expect(metadataWithAI).toHaveBeenCalledTimes(1);

		await rerender({ isOpen: true, documentText: '內容 B' });
		await waitFor(() => expect(metadataWithAI).toHaveBeenCalledTimes(2));
		expect(metadataWithAI).toHaveBeenLastCalledWith('內容 B');
	});

	it('shows a loading state while analyzing', async () => {
		vi.mocked(metadataWithAI).mockImplementation(() => new Promise(() => {}));

		render(AIMetadataDialog, { props: { isOpen: true, documentText: '內容' } });

		expect(await screen.findByText(/分析中/)).toBeInTheDocument();
	});

	it('treats a success response without result as a failure', async () => {
		vi.mocked(metadataWithAI).mockResolvedValue({ success: true });

		render(AIMetadataDialog, { props: { isOpen: true, documentText: '內容' } });

		await waitFor(() => expect(toastError).toHaveBeenCalledWith('AI 文件分析失敗'));
	});
});
