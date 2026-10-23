import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/svelte';

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$lib/auth', () => ({ post: vi.fn(), del: vi.fn() }));
vi.mock('$lib/api/documents', () => ({ getDocuments: vi.fn() }));

import Page from './+page.svelte';
import { goto } from '$app/navigation';
import { post, del } from '$lib/auth';
import { getDocuments, type Document } from '$lib/api/documents';

function doc(overrides: Partial<Document> = {}): Document {
	return {
		id: 'd1',
		title: 'My Doc',
		is_owner: true,
		owner: { id: 1, username: 'alice', email: null },
		permission: 'owner' as Document['permission'],
		can_write: true,
		...overrides
	};
}

function pageOf(items: Document[], { page = 1, total_pages = 1, total = items.length } = {}) {
	return { items, total, page, page_size: 20, total_pages };
}

describe('Dashboard page', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('shows a loading state, then the documents', async () => {
		vi.mocked(getDocuments).mockResolvedValue(pageOf([doc()]));

		render(Page);

		expect(screen.getByText('Loading documents...')).toBeInTheDocument();
		const link = await screen.findByRole('link', { name: /My Doc/ });
		expect(link).toHaveAttribute('href', '/docs/d1');
		expect(getDocuments).toHaveBeenCalledWith(1);
		expect(screen.getByText('alice')).toBeInTheDocument();
	});

	it('shows the empty state', async () => {
		vi.mocked(getDocuments).mockResolvedValue(pageOf([]));

		render(Page);

		expect(await screen.findByText('No documents yet')).toBeInTheDocument();
	});

	it('labels shared documents with their permission and hides delete for them', async () => {
		vi.mocked(getDocuments).mockResolvedValue(
			pageOf([
				doc({ id: 'own', title: 'Own' }),
				doc({ id: 'w', title: 'Shared Write', is_owner: false, permission: 'write' }),
				doc({
					id: 'r',
					title: 'Shared Read',
					is_owner: false,
					permission: 'read',
					can_write: false
				})
			])
		);

		render(Page);
		await screen.findByText('Own');

		const row = (title: string) => screen.getByText(title).closest('li')!;
		expect(within(row('Shared Write')).getByText('Can Edit')).toBeInTheDocument();
		expect(within(row('Shared Read')).getByText('View Only')).toBeInTheDocument();
		expect(within(row('Own')).queryByText(/Can Edit|View Only/)).toBeNull();
		expect(within(row('Own')).getByTitle('Delete document')).toBeInTheDocument();
		expect(within(row('Shared Write')).queryByTitle('Delete document')).toBeNull();
	});

	it('creates an untitled document and opens it', async () => {
		vi.mocked(getDocuments).mockResolvedValue(pageOf([]));
		vi.mocked(post).mockResolvedValue({ id: 'new-id' });
		render(Page);
		await screen.findByText('No documents yet');

		await fireEvent.click(screen.getByText('New Document'));

		await waitFor(() => expect(goto).toHaveBeenCalledWith('/docs/new-id'));
		expect(post).toHaveBeenCalledWith('/documents/', { title: 'Untitled Document' });
	});

	it('deletes after confirmation and reloads the current page', async () => {
		vi.mocked(getDocuments).mockResolvedValue(pageOf([doc(), doc({ id: 'd2', title: 'Other' })]));
		vi.mocked(del).mockResolvedValue(null);
		render(Page);
		await screen.findByText('My Doc');

		await fireEvent.click(
			within(screen.getByText('My Doc').closest('li')!).getByTitle('Delete document')
		);
		await fireEvent.click(within(screen.getByRole('alertdialog')).getByText('刪除'));

		await waitFor(() => expect(del).toHaveBeenCalledWith('/documents/d1/'));
		expect(getDocuments).toHaveBeenLastCalledWith(1);
	});

	it('cancelling the confirmation does not delete', async () => {
		vi.mocked(getDocuments).mockResolvedValue(pageOf([doc()]));
		render(Page);
		await screen.findByText('My Doc');

		await fireEvent.click(screen.getByTitle('Delete document'));
		await fireEvent.click(within(screen.getByRole('alertdialog')).getByText('取消'));

		expect(del).not.toHaveBeenCalled();
	});

	it('goes back a page after deleting the last document on it', async () => {
		vi.mocked(getDocuments)
			.mockResolvedValueOnce(pageOf([doc()], { page: 1, total_pages: 2, total: 21 }))
			.mockResolvedValueOnce(
				pageOf([doc({ id: 'last', title: 'Last One' })], { page: 2, total_pages: 2, total: 21 })
			)
			.mockResolvedValue(pageOf([doc()], { page: 1, total_pages: 1, total: 20 }));
		vi.mocked(del).mockResolvedValue(null);
		render(Page);
		await screen.findByText('共 21 個文件');

		await fireEvent.click(screen.getByText('下一頁'));
		await screen.findByText('Last One');
		expect(getDocuments).toHaveBeenLastCalledWith(2);

		await fireEvent.click(screen.getByTitle('Delete document'));
		await fireEvent.click(within(screen.getByRole('alertdialog')).getByText('刪除'));

		await waitFor(() => expect(getDocuments).toHaveBeenLastCalledWith(1));
	});

	it('paginates with disabled buttons at the edges', async () => {
		vi.mocked(getDocuments)
			.mockResolvedValueOnce(pageOf([doc()], { page: 1, total_pages: 2, total: 25 }))
			.mockResolvedValueOnce(
				pageOf([doc({ id: 'p2', title: 'Page Two' })], { page: 2, total_pages: 2, total: 25 })
			)
			.mockResolvedValueOnce(pageOf([doc()], { page: 1, total_pages: 2, total: 25 }));
		render(Page);

		await screen.findByText('1 / 2');
		expect(screen.getByText('上一頁')).toBeDisabled();
		expect(screen.getByText('下一頁')).not.toBeDisabled();

		await fireEvent.click(screen.getByText('下一頁'));
		await screen.findByText('2 / 2');
		expect(screen.getByText('下一頁')).toBeDisabled();
		expect(screen.getByText('上一頁')).not.toBeDisabled();

		await fireEvent.click(screen.getByText('上一頁'));
		await waitFor(() => expect(getDocuments).toHaveBeenLastCalledWith(1));
	});

	it('hides pagination for a single page', async () => {
		vi.mocked(getDocuments).mockResolvedValue(pageOf([doc()]));
		render(Page);
		await screen.findByText('My Doc');

		expect(screen.queryByText('下一頁')).toBeNull();
	});
});
