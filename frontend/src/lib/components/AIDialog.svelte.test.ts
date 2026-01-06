import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import AIDialog from './AIDialog.svelte';

// Mock AI API
vi.mock('$lib/ai', () => ({
	processWithAI: vi.fn()
}));

// Mock toast
vi.mock('@zerodevx/svelte-toast', () => ({
	toast: { push: vi.fn() }
}));

// Mock $app/environment
vi.mock('$app/environment', () => ({
	browser: true
}));

import { processWithAI } from '$lib/ai';
import { toast } from '@zerodevx/svelte-toast';

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
		expect(screen.queryByText('AI Writing Assistant')).toBeNull();
	});

	it('should render when isOpen is true', () => {
		render(AIDialog, {
			props: {
				isOpen: true,
				selectedText: 'Test text',
				onApply: vi.fn()
			}
		});
		expect(screen.getByText('AI Writing Assistant')).toBeInTheDocument();
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

		const summarizeBtn = screen.getByText('Summarize');
		const polishBtn = screen.getByText('Polish');

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

		const summarizeBtn = screen.getByText('Summarize');
		const polishBtn = screen.getByText('Polish');

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

		await fireEvent.click(screen.getByText('Summarize'));

		expect(screen.getByText('AI processing...')).toBeInTheDocument();
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

		await fireEvent.click(screen.getByText('Summarize'));

		await waitFor(() => {
			expect(screen.getByText('AI result text')).toBeInTheDocument();
			expect(screen.getByText('Apply Result')).toBeInTheDocument();
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

		await fireEvent.click(screen.getByText('Summarize'));

		await waitFor(() => {
			expect(toast.push).toHaveBeenCalledWith('Test error', expect.any(Object));
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

		await fireEvent.click(screen.getByText('Summarize'));

		await waitFor(() => {
			expect(toast.push).toHaveBeenCalledWith(
				'Request timed out, please try again',
				expect.any(Object)
			);
		});
	});

	it('should call onApply when Apply Result is clicked', async () => {
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

		await fireEvent.click(screen.getByText('Summarize'));

		await waitFor(() => {
			expect(screen.getByText('Apply Result')).toBeInTheDocument();
		});

		await fireEvent.click(screen.getByText('Apply Result'));

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

		await fireEvent.click(screen.getByText('Summarize'));

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

		await fireEvent.click(screen.getByText('Polish'));

		expect(processWithAI).toHaveBeenCalledWith({
			action: 'polish',
			text: 'Test text to polish'
		});
	});
});
