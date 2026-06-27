import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import AIAskDialog from './AIAskDialog.svelte';

// Mock AI API
vi.mock('$lib/ai', () => ({
	askWithAI: vi.fn()
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

import { askWithAI } from '$lib/ai';
import { toastError } from '$lib/toast';

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

	it('should not call API when question is empty (送出 disabled)', async () => {
		render(AIAskDialog, {
			props: { isOpen: true, documentText: '文件內容' }
		});

		// 空問題時送出按鈕為 disabled，點擊不觸發 API
		await fireEvent.click(screen.getByText('送出'));

		expect(askWithAI).not.toHaveBeenCalled();
	});

	it('should call askWithAI with question and document text', async () => {
		vi.mocked(askWithAI).mockResolvedValue({ success: true, answer: '答案' });

		render(AIAskDialog, {
			props: { isOpen: true, documentText: '這份文件介紹 Docker' }
		});

		const textarea = screen.getByPlaceholderText('例如：這份文件的重點是什麼？');
		await fireEvent.input(textarea, { target: { value: '重點是什麼？' } });
		await fireEvent.click(screen.getByText('送出'));

		expect(askWithAI).toHaveBeenCalledWith('重點是什麼？', '這份文件介紹 Docker');
	});

	it('should render answer when API succeeds', async () => {
		vi.mocked(askWithAI).mockResolvedValue({
			success: true,
			answer: '這份文件介紹容器化技術'
		});

		render(AIAskDialog, {
			props: { isOpen: true, documentText: 'Docker 文件' }
		});

		const textarea = screen.getByPlaceholderText('例如：這份文件的重點是什麼？');
		await fireEvent.input(textarea, { target: { value: '這是什麼？' } });
		await fireEvent.click(screen.getByText('送出'));

		await waitFor(() => {
			expect(screen.getByText('回答')).toBeInTheDocument();
			expect(screen.getByText('這份文件介紹容器化技術')).toBeInTheDocument();
		});
	});

	it('should show error toast when API fails', async () => {
		vi.mocked(askWithAI).mockResolvedValue({ success: false, error: 'Ask error' });

		render(AIAskDialog, {
			props: { isOpen: true, documentText: '文件內容' }
		});

		const textarea = screen.getByPlaceholderText('例如：這份文件的重點是什麼？');
		await fireEvent.input(textarea, { target: { value: '問題' } });
		await fireEvent.click(screen.getByText('送出'));

		await waitFor(() => {
			expect(toastError).toHaveBeenCalledWith('Ask error');
		});
	});
});
