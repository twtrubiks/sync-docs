import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/auth', () => ({
	get: vi.fn()
}));

import { get } from '$lib/auth';
import { getDocuments } from '$lib/api/documents';

const mockGet = vi.mocked(get);

describe('documents API', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('calls get with correct URL and pagination params', async () => {
		const response = { items: [], total: 0, page: 2, page_size: 10, total_pages: 0 };
		mockGet.mockResolvedValueOnce(response);

		const result = await getDocuments(2, 10);

		expect(mockGet).toHaveBeenCalledWith('/documents/?page=2&page_size=10');
		expect(result).toEqual(response);
	});

	it('uses default page=1 and pageSize=20', async () => {
		mockGet.mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 20, total_pages: 0 });

		await getDocuments();

		expect(mockGet).toHaveBeenCalledWith('/documents/?page=1&page_size=20');
	});

	it('returns PaginatedDocumentResponse structure', async () => {
		const response = {
			items: [{ id: '1', title: 'Doc', is_owner: true, owner: { id: 1, username: 'u', email: null }, permission: null, can_write: true }],
			total: 1,
			page: 1,
			page_size: 20,
			total_pages: 1
		};
		mockGet.mockResolvedValueOnce(response);

		const result = await getDocuments();

		expect(result.items).toHaveLength(1);
		expect(result.total).toBe(1);
	});
});
