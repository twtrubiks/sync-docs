import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import AIAskDialog from './AIAskDialog.svelte';

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

describe('AIAskDialog', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('should not render when isOpen is false', () => {
		render(AIAskDialog, {
			props: { isOpen: false, documentText: '文件內容' }
		});
		expect(screen.queryByText('文件問答')).toBeNull();
	});

	it('should render question input when open', () => {
		render(AIAskDialog, {
			props: { isOpen: true, documentText: '文件內容' }
		});
		expect(screen.getByText('文件問答')).toBeInTheDocument();
		expect(screen.getByPlaceholderText('例如：這份文件的重點是什麼？')).toBeInTheDocument();
	});

	it('should not call onAsk when question is empty (送出 disabled)', async () => {
		const onAsk = vi.fn().mockReturnValue(true);
		render(AIAskDialog, {
			props: { isOpen: true, documentText: '文件內容', onAsk }
		});

		// 空問題時送出按鈕為 disabled，點擊不觸發串流
		await fireEvent.click(screen.getByText('送出'));

		expect(onAsk).not.toHaveBeenCalled();
	});

	it('should call onAsk with question and document text', async () => {
		const onAsk = vi.fn().mockReturnValue(true);
		render(AIAskDialog, {
			props: { isOpen: true, documentText: '這份文件介紹 Docker', onAsk }
		});

		const textarea = screen.getByPlaceholderText('例如：這份文件的重點是什麼？');
		await fireEvent.input(textarea, { target: { value: '重點是什麼？' } });
		await fireEvent.click(screen.getByText('送出'));

		expect(onAsk).toHaveBeenCalledWith('重點是什麼？', '這份文件介紹 Docker');
	});

	it('should show spinner while streaming with no text yet', () => {
		render(AIAskDialog, {
			props: { isOpen: true, documentText: '文件內容', streaming: true, streamText: '' }
		});
		expect(screen.getByText('AI 回答中...')).toBeInTheDocument();
	});

	it('should render streamed answer when streamText provided', () => {
		render(AIAskDialog, {
			props: {
				isOpen: true,
				documentText: 'Docker 文件',
				streaming: false,
				streamText: '這份文件介紹容器化技術'
			}
		});

		expect(screen.getByText('回答')).toBeInTheDocument();
		expect(screen.getByText(/這份文件介紹容器化技術/)).toBeInTheDocument();
	});

	it('should show stop button while streaming and call onCancelStream when clicked', async () => {
		const onCancelStream = vi.fn();
		render(AIAskDialog, {
			props: {
				isOpen: true,
				documentText: '文件內容',
				streaming: true,
				streamText: '部分答案',
				onCancelStream
			}
		});

		const stopButton = screen.getByText('停止生成');
		expect(stopButton).toBeInTheDocument();

		await fireEvent.click(stopButton);
		expect(onCancelStream).toHaveBeenCalled();
	});
});
