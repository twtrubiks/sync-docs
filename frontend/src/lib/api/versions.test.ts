import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/auth', () => ({
	get: vi.fn(),
	post: vi.fn()
}));

import { get, post } from '$lib/auth';
import { getVersions, getVersionDetail, restoreVersion } from '$lib/api/versions';

const mockGet = vi.mocked(get);
const mockPost = vi.mocked(post);

describe('versions API', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('getVersions calls get with correct URL and pagination', async () => {
		mockGet.mockResolvedValueOnce({
			items: [],
			total: 0,
			page: 2,
			page_size: 10,
			total_pages: 0
		});

		const result = await getVersions('doc-1', 2, 10);

		expect(mockGet).toHaveBeenCalledWith('/documents/doc-1/versions/?page=2&page_size=10');
		expect(result.items).toEqual([]);
	});

	it('getVersionDetail calls get with correct URL', async () => {
		mockGet.mockResolvedValueOnce({
			id: 'v-1',
			version_number: 1,
			created_at: '2024-01-01T00:00:00Z',
			created_by_username: 'alice',
			content: { ops: [] }
		});

		await getVersionDetail('doc-1', 'v-1');

		expect(mockGet).toHaveBeenCalledWith('/documents/doc-1/versions/v-1/');
	});

	it('restoreVersion calls post with correct URL and empty body', async () => {
		mockPost.mockResolvedValueOnce({
			success: true,
			message: 'restored',
			new_version_number: 3
		});

		await restoreVersion('doc-1', 'v-1');

		expect(mockPost).toHaveBeenCalledWith('/documents/doc-1/versions/v-1/restore/', {});
	});
});
