import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import AIDialog from './AIDialog.svelte';

// Mock AI API（summarize/polish 改走 WebSocket 串流，僅 proofread 仍用 HTTP）
vi.mock('$lib/ai', () => ({
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

import { proofreadWithAI } from '$lib/ai';
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

	// summarize/polish 改走 WebSocket 串流：透過 onStream callback + streaming/streamText props
	const streamProps = (overrides = {}) => ({
		isOpen: true,
		selectedText: 'Test text',
		onApply: vi.fn(),
		onStream: vi.fn(() => true),
		onCancelStream: vi.fn(),
		streaming: false,
		streamText: '',
		...overrides
	});

	it('should call onStream with correct params for summarize', async () => {
		const onStream = vi.fn(() => true);
		render(AIDialog, {
			props: streamProps({ selectedText: 'Test text to summarize', onStream })
		});

		await fireEvent.click(screen.getByText('摘要'));

		expect(onStream).toHaveBeenCalledWith('summarize', 'Test text to summarize');
	});

	it('should call onStream with correct params for polish', async () => {
		const onStream = vi.fn(() => true);
		render(AIDialog, {
			props: streamProps({ selectedText: 'Test text to polish', onStream })
		});

		await fireEvent.click(screen.getByText('潤稿'));

		expect(onStream).toHaveBeenCalledWith('polish', 'Test text to polish');
	});

	it('should show streaming loading state before first chunk', async () => {
		const { rerender } = render(AIDialog, { props: streamProps() });

		await fireEvent.click(screen.getByText('摘要'));
		// 父層開始串流但尚無 chunk
		await rerender(streamProps({ streaming: true }));

		expect(screen.getByText('AI 生成中...')).toBeInTheDocument();
	});

	it('should render streamed text and apply it', async () => {
		const onApply = vi.fn();
		const { rerender } = render(AIDialog, { props: streamProps({ onApply }) });

		await fireEvent.click(screen.getByText('摘要'));
		// 串流完成：父層提供完整結果
		await rerender(streamProps({ onApply, streaming: false, streamText: 'AI 串流結果' }));

		await waitFor(() => {
			expect(screen.getByText('AI 串流結果')).toBeInTheDocument();
			expect(screen.getByText('套用結果')).toBeInTheDocument();
		});

		await fireEvent.click(screen.getByText('套用結果'));
		expect(onApply).toHaveBeenCalledWith('AI 串流結果');
	});

	it('should request cancel when 停止生成 is clicked', async () => {
		const onCancelStream = vi.fn();
		const { rerender } = render(AIDialog, { props: streamProps({ onCancelStream }) });

		await fireEvent.click(screen.getByText('摘要'));
		await rerender(streamProps({ onCancelStream, streaming: true, streamText: '部分結果' }));

		await fireEvent.click(screen.getByText('停止生成'));
		expect(onCancelStream).toHaveBeenCalled();
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
