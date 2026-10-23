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

import { proofreadWithAI, type WritingIssue } from '$lib/ai';
import { toastError, toastWarning } from '$lib/toast';

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
	// ── 變異測試補強 ──

	const proofreadResult = (issues: WritingIssue[], overall_score = 70) => ({
		success: true,
		result: { issues, overall_score }
	});

	it('shows a placeholder and disables actions for whitespace-only selections', () => {
		render(AIDialog, { props: streamProps({ selectedText: '' }) });
		expect(screen.getByText('（未選取文字）')).toBeInTheDocument();

		document.body.innerHTML = '';
		render(AIDialog, { props: streamProps({ selectedText: '   ' }) });
		for (const label of ['摘要', '潤稿', '校對']) {
			expect(screen.getByText(label).closest('button')).toBeDisabled();
		}
	});

	it('disables every action while a stream is running', async () => {
		const { rerender } = render(AIDialog, { props: streamProps() });

		await fireEvent.click(screen.getByText('摘要'));
		await rerender(streamProps({ streaming: true }));

		for (const label of ['摘要', '潤稿', '校對']) {
			expect(screen.getByText(label).closest('button')).toBeDisabled();
		}
	});

	it('labels polish results and applies them', async () => {
		const onApply = vi.fn();
		const { rerender } = render(AIDialog, { props: streamProps({ onApply }) });

		await fireEvent.click(screen.getByText('潤稿'));
		await rerender(streamProps({ onApply, streaming: true }));
		expect(screen.getByText('AI 生成中...')).toBeInTheDocument();
		expect(screen.getByText('停止生成')).toBeInTheDocument();

		await rerender(streamProps({ onApply, streaming: false, streamText: '潤飾後' }));
		expect(screen.getByText('潤稿結果')).toBeInTheDocument();
		expect(screen.queryByText('摘要結果')).toBeNull();
		await fireEvent.click(screen.getByText('套用結果'));

		expect(onApply).toHaveBeenCalledWith('潤飾後');
		expect(screen.queryByRole('heading')).toBeNull(); // 套用後關閉
	});

	it('labels summary results as 摘要結果', async () => {
		const { rerender } = render(AIDialog, { props: streamProps() });

		await fireEvent.click(screen.getByText('摘要'));
		await rerender(streamProps({ streamText: '重點' }));

		expect(screen.getByText('摘要結果')).toBeInTheDocument();
	});

	it('resets when the stream could not be started', async () => {
		const { rerender } = render(AIDialog, { props: streamProps({ onStream: vi.fn(() => false) }) });

		await fireEvent.click(screen.getByText('摘要'));
		await rerender(streamProps({ onStream: vi.fn(() => false), streamText: '舊的結果' }));

		expect(screen.queryByText('舊的結果')).toBeNull();
		expect(screen.queryByText('套用結果')).toBeNull();
	});

	it('closing during a stream cancels it; closing afterwards does not', async () => {
		const onCancelStream = vi.fn();
		const { rerender } = render(AIDialog, { props: streamProps({ onCancelStream }) });
		await fireEvent.click(screen.getByText('摘要'));
		await rerender(streamProps({ onCancelStream, streaming: true, streamText: '部分' }));

		await fireEvent.click(screen.getByLabelText('Close dialog'));

		expect(onCancelStream).toHaveBeenCalledTimes(1);
		expect(screen.queryByText('部分')).toBeNull();

		document.body.innerHTML = '';
		const onCancel2 = vi.fn();
		const r2 = render(AIDialog, { props: streamProps({ onCancelStream: onCancel2 }) });
		await fireEvent.click(screen.getByText('摘要'));
		await r2.rerender(streamProps({ onCancelStream: onCancel2, streamText: '完成' }));
		await fireEvent.click(screen.getByText('取消'));

		expect(onCancel2).not.toHaveBeenCalled();
		expect(screen.queryByText('完成')).toBeNull();
	});

	it('shows severity labels and keeps unknown severities as-is', async () => {
		vi.mocked(proofreadWithAI).mockResolvedValue(
			proofreadResult([
				{ original: 'a', suggestion: 'A1', reason: 'r1', severity: 'info' },
				{ original: 'b', suggestion: 'B1', reason: 'r2', severity: 'warning' },
				{ original: 'c', suggestion: 'C1', reason: 'r3', severity: 'error' },
				// 後端未來若新增嚴重度，前端應原樣顯示
				{
					original: 'd',
					suggestion: 'D1',
					reason: 'r4',
					severity: 'critical'
				} as unknown as WritingIssue
			])
		);
		render(AIDialog, { props: streamProps({ selectedText: 'abcd' }) });

		await fireEvent.click(screen.getByText('校對'));

		for (const label of ['提示', '建議', '錯誤', 'critical']) {
			expect(await screen.findByText(label)).toBeInTheDocument();
		}
	});

	it('applies each issue once and warns when its original text is gone', async () => {
		const onApply = vi.fn();
		vi.mocked(proofreadWithAI).mockResolvedValue(
			proofreadResult([
				{ original: '甲乙', suggestion: '丙', reason: 'r1', severity: 'warning' },
				{ original: '乙丁', suggestion: '戊', reason: 'r2', severity: 'warning' }
			])
		);
		render(AIDialog, { props: streamProps({ selectedText: '甲乙丁', onApply }) });
		await fireEvent.click(screen.getByText('校對'));
		const [first, second] = await screen.findAllByText('套用');

		expect(screen.getByText('套用變更到文件').closest('button')).toBeDisabled();
		await fireEvent.click(first);
		expect(first).toBeDisabled();
		expect(first).toHaveTextContent('已套用');

		// 第一項把「乙」改掉了，第二項的原文已不存在
		await fireEvent.click(second);
		expect(toastWarning).toHaveBeenCalledWith('找不到原文片段，可能已被其他建議修改');
		expect(second).toHaveTextContent('套用');

		await fireEvent.click(screen.getByText('套用變更到文件'));
		expect(onApply).toHaveBeenCalledWith('丙丁');
	});

	it.each([
		[{ success: false }, 'AI proofreading failed'],
		[{ success: true }, 'AI proofreading failed']
	])('reports unusable proofread responses (%o)', async (response, message) => {
		vi.mocked(proofreadWithAI).mockResolvedValue(response);
		render(AIDialog, { props: streamProps() });

		await fireEvent.click(screen.getByText('校對'));

		await waitFor(() => expect(toastError).toHaveBeenCalledWith(message));
		expect(screen.queryByText('校對結果')).toBeNull();
	});

	it.each([
		[
			Object.assign(new Error('aborted'), { name: 'AbortError' }),
			'Request timed out, please try again'
		],
		[new Error('network'), 'AI processing request failed']
	])('reports thrown proofread errors (%s)', async (error, message) => {
		vi.mocked(proofreadWithAI).mockRejectedValue(error);
		render(AIDialog, { props: streamProps() });

		await fireEvent.click(screen.getByText('校對'));

		await waitFor(() => expect(toastError).toHaveBeenCalledWith(message));
		expect(screen.getByText('校對').closest('button')).not.toBeDisabled();
	});
});
