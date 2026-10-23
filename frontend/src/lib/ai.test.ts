import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('$lib/auth', () => ({
	post: vi.fn()
}));

import { post } from '$lib/auth';
import { proofreadWithAI, metadataWithAI } from '$lib/ai';

const mockPost = vi.mocked(post);

describe.each([
	['proofreadWithAI', proofreadWithAI, '/ai/proofread'],
	['metadataWithAI', metadataWithAI, '/ai/metadata']
])('%s', (_name, call, url) => {
	beforeEach(() => {
		vi.clearAllMocks();
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('posts the text and returns the response', async () => {
		const response = { success: true };
		mockPost.mockResolvedValue(response);

		await expect(call('一段文字')).resolves.toBe(response);
		expect(mockPost).toHaveBeenCalledWith(url, { text: '一段文字' }, expect.any(AbortSignal));
	});

	it('aborts the request after 30 seconds when no signal is given', async () => {
		mockPost.mockImplementation(() => new Promise(() => {}));

		void call('文字');
		const signal = mockPost.mock.calls[0][2] as AbortSignal;

		await vi.advanceTimersByTimeAsync(29999);
		expect(signal.aborted).toBe(false);
		await vi.advanceTimersByTimeAsync(1);
		expect(signal.aborted).toBe(true);
	});

	it('clears the timeout once the request settles', async () => {
		mockPost.mockResolvedValue({ success: true });

		await call('文字');
		const signal = mockPost.mock.calls[0][2] as AbortSignal;
		await vi.advanceTimersByTimeAsync(60000);

		expect(signal.aborted).toBe(false);
		expect(vi.getTimerCount()).toBe(0);
	});

	it('uses the caller signal without starting its own timer', async () => {
		mockPost.mockResolvedValue({ success: true });
		const controller = new AbortController();

		await call('文字', controller.signal);

		expect(mockPost).toHaveBeenCalledWith(url, { text: '文字' }, controller.signal);
		expect(vi.getTimerCount()).toBe(0);
	});
});
