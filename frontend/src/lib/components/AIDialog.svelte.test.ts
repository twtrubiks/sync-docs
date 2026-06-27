import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import AIDialog from './AIDialog.svelte';

// Mock AI API
vi.mock('$lib/ai', () => ({
	processWithAI: vi.fn(),
	proofreadWithAI: vi.fn()
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

import { processWithAI, proofreadWithAI } from '$lib/ai';
import { toastError } from '$lib/toast';

describe('AIDialog', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('should not render when isOpen is false', () => {
		render(AIDialog, {
			props: {
				isOpen: false,
				selectedText: '',
				onApply: vi.fn()
			}
		});
		expect(screen.queryByText('AI 寫作助手')).toBeNull();
	});

	it('should render when isOpen is true', () => {
		render(AIDialog, {
			props: {
				isOpen: true,
				selectedText: 'Test text',
				onApply: vi.fn()
			}
		});
		expect(screen.getByText('AI 寫作助手')).toBeInTheDocument();
		expect(screen.getByText('Test text')).toBeInTheDocument();
	});

	it('should disable buttons when no text is selected', () => {
		render(AIDialog, {
			props: {
				isOpen: true,
				selectedText: '',
				onApply: vi.fn()
			}
		});

		const summarizeBtn = screen.getByText('摘要');
		const polishBtn = screen.getByText('潤稿');

		expect(summarizeBtn).toBeDisabled();
		expect(polishBtn).toBeDisabled();
	});

	it('should enable buttons when text is selected', () => {
		render(AIDialog, {
			props: {
				isOpen: true,
				selectedText: 'Test text',
				onApply: vi.fn()
			}
		});

		const summarizeBtn = screen.getByText('摘要');
		const polishBtn = screen.getByText('潤稿');

		expect(summarizeBtn).not.toBeDisabled();
		expect(polishBtn).not.toBeDisabled();
	});

	it('should show loading state when processing', async () => {
		vi.mocked(processWithAI).mockImplementation(
			() => new Promise(() => {}) // Never resolves
		);

		render(AIDialog, {
			props: {
				isOpen: true,
				selectedText: 'Test text',
				onApply: vi.fn()
			}
		});

		await fireEvent.click(screen.getByText('摘要'));

		expect(screen.getByText('AI 處理中...')).toBeInTheDocument();
	});

	it('should show result when API succeeds', async () => {
		vi.mocked(processWithAI).mockResolvedValue({
			success: true,
			result: 'AI result text',
			action: 'summarize'
		});

		render(AIDialog, {
			props: {
				isOpen: true,
				selectedText: 'Test text',
				onApply: vi.fn()
			}
		});

		await fireEvent.click(screen.getByText('摘要'));

		await waitFor(() => {
			expect(screen.getByText('AI result text')).toBeInTheDocument();
			expect(screen.getByText('套用結果')).toBeInTheDocument();
		});
	});

	it('should show error toast when API fails', async () => {
		vi.mocked(processWithAI).mockResolvedValue({
			success: false,
			result: '',
			action: 'summarize',
			error: 'Test error'
		});

		render(AIDialog, {
			props: {
				isOpen: true,
				selectedText: 'Test text',
				onApply: vi.fn()
			}
		});

		await fireEvent.click(screen.getByText('摘要'));

		await waitFor(() => {
			expect(toastError).toHaveBeenCalledWith('Test error');
		});
	});

	it('should handle timeout error', async () => {
		const abortError = new Error('Aborted');
		abortError.name = 'AbortError';
		vi.mocked(processWithAI).mockRejectedValue(abortError);

		render(AIDialog, {
			props: {
				isOpen: true,
				selectedText: 'Test text',
				onApply: vi.fn()
			}
		});

		await fireEvent.click(screen.getByText('摘要'));

		await waitFor(() => {
			expect(toastError).toHaveBeenCalledWith('Request timed out, please try again');
		});
	});

	it('should call onApply when 套用結果 is clicked', async () => {
		const onApply = vi.fn();
		vi.mocked(processWithAI).mockResolvedValue({
			success: true,
			result: 'AI result text',
			action: 'summarize'
		});

		render(AIDialog, {
			props: {
				isOpen: true,
				selectedText: 'Test text',
				onApply
			}
		});

		await fireEvent.click(screen.getByText('摘要'));

		await waitFor(() => {
			expect(screen.getByText('套用結果')).toBeInTheDocument();
		});

		await fireEvent.click(screen.getByText('套用結果'));

		expect(onApply).toHaveBeenCalledWith('AI result text');
	});

	it('should call processWithAI with correct parameters for summarize', async () => {
		vi.mocked(processWithAI).mockResolvedValue({
			success: true,
			result: 'Summary result',
			action: 'summarize'
		});

		render(AIDialog, {
			props: {
				isOpen: true,
				selectedText: 'Test text to summarize',
				onApply: vi.fn()
			}
		});

		await fireEvent.click(screen.getByText('摘要'));

		expect(processWithAI).toHaveBeenCalledWith({
			action: 'summarize',
			text: 'Test text to summarize'
		});
	});

	it('should call processWithAI with correct parameters for polish', async () => {
		vi.mocked(processWithAI).mockResolvedValue({
			success: true,
			result: 'Polished result',
			action: 'polish'
		});

		render(AIDialog, {
			props: {
				isOpen: true,
				selectedText: 'Test text to polish',
				onApply: vi.fn()
			}
		});

		await fireEvent.click(screen.getByText('潤稿'));

		expect(processWithAI).toHaveBeenCalledWith({
			action: 'polish',
			text: 'Test text to polish'
		});
	});

	it('should call proofreadWithAI with selected text', async () => {
		vi.mocked(proofreadWithAI).mockResolvedValue({
			success: true,
			result: { issues: [], overall_score: 90 }
		});

		render(AIDialog, {
			props: {
				isOpen: true,
				selectedText: 'Text to proofread',
				onApply: vi.fn()
			}
		});

		await fireEvent.click(screen.getByText('校對'));

		expect(proofreadWithAI).toHaveBeenCalledWith('Text to proofread');
	});

	it('should render proofread issues with score', async () => {
		vi.mocked(proofreadWithAI).mockResolvedValue({
			success: true,
			result: {
				issues: [{ original: '錯字', suggestion: '正字', reason: '用字錯誤', severity: 'warning' }],
				overall_score: 75
			}
		});

		render(AIDialog, {
			props: {
				isOpen: true,
				selectedText: '這是錯字範例',
				onApply: vi.fn()
			}
		});

		await fireEvent.click(screen.getByText('校對'));

		await waitFor(() => {
			expect(screen.getByText('校對結果')).toBeInTheDocument();
			expect(screen.getByText('75')).toBeInTheDocument();
			expect(screen.getByText('正字')).toBeInTheDocument();
			expect(screen.getByText('用字錯誤')).toBeInTheDocument();
		});
	});

	it('should apply an issue via string match and call onApply with corrected text', async () => {
		const onApply = vi.fn();
		vi.mocked(proofreadWithAI).mockResolvedValue({
			success: true,
			result: {
				issues: [{ original: '錯字', suggestion: '正字', reason: '用字錯誤', severity: 'warning' }],
				overall_score: 75
			}
		});

		render(AIDialog, {
			props: {
				isOpen: true,
				selectedText: '這是錯字範例',
				onApply
			}
		});

		await fireEvent.click(screen.getByText('校對'));

		await waitFor(() => {
			expect(screen.getByText('套用')).toBeInTheDocument();
		});

		// 逐項套用：工作文字中以字串比對取代
		await fireEvent.click(screen.getByText('套用'));
		await waitFor(() => {
			expect(screen.getByText('已套用')).toBeInTheDocument();
		});

		// 套用變更到文件
		await fireEvent.click(screen.getByText('套用變更到文件'));
		expect(onApply).toHaveBeenCalledWith('這是正字範例');
	});

	it('should show no-issues message when proofread finds nothing', async () => {
		vi.mocked(proofreadWithAI).mockResolvedValue({
			success: true,
			result: { issues: [], overall_score: 100 }
		});

		render(AIDialog, {
			props: {
				isOpen: true,
				selectedText: '完美的文字',
				onApply: vi.fn()
			}
		});

		await fireEvent.click(screen.getByText('校對'));

		await waitFor(() => {
			expect(screen.getByText('沒有發現明顯問題 🎉')).toBeInTheDocument();
		});
	});

	it('should show error toast when proofread fails', async () => {
		vi.mocked(proofreadWithAI).mockResolvedValue({
			success: false,
			error: 'Proofread error'
		});

		render(AIDialog, {
			props: {
				isOpen: true,
				selectedText: 'Test text',
				onApply: vi.fn()
			}
		});

		await fireEvent.click(screen.getByText('校對'));

		await waitFor(() => {
			expect(toastError).toHaveBeenCalledWith('Proofread error');
		});
	});
});
