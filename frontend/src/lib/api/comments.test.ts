import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/auth', () => ({
	get: vi.fn(),
	post: vi.fn(),
	put: vi.fn(),
	del: vi.fn()
}));

import { get, post, put, del } from '$lib/auth';
import {
	getComments,
	getReplies,
	createComment,
	updateComment,
	deleteComment
} from '$lib/api/comments';

const mockGet = vi.mocked(get);
const mockPost = vi.mocked(post);
const mockPut = vi.mocked(put);
const mockDel = vi.mocked(del);

describe('comments API', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('getComments calls get with correct URL and pagination', async () => {
		mockGet.mockResolvedValueOnce({
			comments: [],
			total: 0,
			page: 2,
			page_size: 10,
			total_pages: 0
		});

		const result = await getComments('doc-1', 2, 10);

		expect(mockGet).toHaveBeenCalledWith('/documents/doc-1/comments/?page=2&page_size=10');
		expect(result.comments).toEqual([]);
	});

	it('getReplies calls get with correct URL', async () => {
		mockGet.mockResolvedValueOnce([]);

		await getReplies('doc-1', 'comment-1');

		expect(mockGet).toHaveBeenCalledWith('/documents/doc-1/comments/comment-1/replies/');
	});

	it('createComment calls post with correct URL and payload', async () => {
		const payload = { content: 'Hello' };
		mockPost.mockResolvedValueOnce({ id: '1', content: 'Hello' });

		await createComment('doc-1', payload);

		expect(mockPost).toHaveBeenCalledWith('/documents/doc-1/comments/', payload);
	});

	it('updateComment calls put with correct URL and payload', async () => {
		const payload = { content: 'Updated' };
		mockPut.mockResolvedValueOnce({ id: '1', content: 'Updated' });

		await updateComment('doc-1', 'comment-1', payload);

		expect(mockPut).toHaveBeenCalledWith('/documents/doc-1/comments/comment-1/', payload);
	});

	it('deleteComment calls del with correct URL', async () => {
		mockDel.mockResolvedValueOnce({ success: true, message: 'deleted' });

		await deleteComment('doc-1', 'comment-1');

		expect(mockDel).toHaveBeenCalledWith('/documents/doc-1/comments/comment-1/');
	});
});
