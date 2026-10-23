import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/svelte';
import CommentPanel from './CommentPanel.svelte';

vi.mock('$lib/api/comments', () => ({
	getComments: vi.fn(),
	getReplies: vi.fn(),
	createComment: vi.fn(),
	updateComment: vi.fn(),
	deleteComment: vi.fn()
}));

vi.mock('$lib/toast', () => ({
	toastSuccess: vi.fn(),
	toastError: vi.fn(),
	toastWarning: vi.fn()
}));

vi.mock('$app/environment', () => ({
	browser: true
}));

import {
	getComments,
	getReplies,
	createComment,
	updateComment,
	deleteComment,
	type Comment
} from '$lib/api/comments';
import { toastSuccess, toastError } from '$lib/toast';

function makeComment(overrides: Partial<Comment> = {}): Comment {
	return {
		id: 'c1',
		content: 'First comment',
		author_username: 'alice',
		created_at: '2026-03-01T10:00:00Z',
		updated_at: '2026-03-01T10:00:00Z',
		parent_id: null,
		reply_count: 0,
		is_author: true,
		can_delete: true,
		...overrides
	};
}

function page(comments: Comment[], { page = 1, total_pages = 1, total = comments.length } = {}) {
	return { comments, total, page, page_size: 20, total_pages };
}

const defaultProps = {
	documentId: 'doc-1',
	isOpen: true,
	canWrite: true,
	currentUserId: '1',
	isOwner: false
};

async function renderPanel(props: Partial<typeof defaultProps> = {}) {
	const result = render(CommentPanel, { props: { ...defaultProps, ...props } });
	await waitFor(() => expect(getComments).toHaveBeenCalled());
	await waitFor(() => expect(screen.queryByText('載入中...')).toBeNull());
	return result;
}

describe('CommentPanel', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		vi.mocked(getComments).mockResolvedValue(page([makeComment()]));
	});

	describe('loading', () => {
		it('loads the first page when opened and shows the total', async () => {
			vi.mocked(getComments).mockResolvedValue(
				page([makeComment(), makeComment({ id: 'c2', content: 'Second' })])
			);

			await renderPanel();

			expect(getComments).toHaveBeenCalledWith('doc-1', 1);
			expect(screen.getByText('First comment')).toBeInTheDocument();
			expect(screen.getByText('Second')).toBeInTheDocument();
			expect(screen.getByRole('heading', { name: '評論 (2)' })).toBeInTheDocument();
		});

		it('does not load while closed', () => {
			render(CommentPanel, { props: { ...defaultProps, isOpen: false } });

			expect(getComments).not.toHaveBeenCalled();
		});

		it('shows the empty state without a count', async () => {
			vi.mocked(getComments).mockResolvedValue(page([]));

			await renderPanel();

			expect(screen.getByText('尚無評論')).toBeInTheDocument();
			expect(screen.getByRole('heading', { name: '評論' })).toBeInTheDocument();
		});

		it('reports load failures', async () => {
			vi.mocked(getComments).mockRejectedValue(new Error('boom'));

			await renderPanel();

			expect(toastError).toHaveBeenCalledWith('載入評論失敗');
		});

		it('loads more pages and appends them', async () => {
			vi.mocked(getComments)
				.mockResolvedValueOnce(page([makeComment()], { page: 1, total_pages: 2, total: 2 }))
				.mockResolvedValueOnce(
					page([makeComment({ id: 'c2', content: 'Older' })], { page: 2, total_pages: 2, total: 2 })
				);

			await renderPanel();
			await fireEvent.click(screen.getByText('載入更多評論'));

			await waitFor(() => expect(screen.getByText('Older')).toBeInTheDocument());
			expect(getComments).toHaveBeenLastCalledWith('doc-1', 2);
			expect(screen.getByText('First comment')).toBeInTheDocument();
			expect(screen.queryByText('載入更多評論')).toBeNull();
		});
	});

	describe('permissions', () => {
		it('hides the composer and reply action for read-only users', async () => {
			vi.mocked(getComments).mockResolvedValue(
				page([makeComment({ is_author: false, can_delete: false })])
			);

			await renderPanel({ canWrite: false });

			expect(screen.queryByPlaceholderText('輸入評論...')).toBeNull();
			expect(screen.queryByText('回覆')).toBeNull();
			expect(screen.queryByText('編輯')).toBeNull();
			expect(screen.queryByText('刪除')).toBeNull();
		});

		it('shows edit only for the author and delete when allowed', async () => {
			vi.mocked(getComments).mockResolvedValue(
				page([makeComment({ is_author: false, can_delete: true })])
			);

			await renderPanel();

			expect(screen.getByText('回覆')).toBeInTheDocument();
			expect(screen.queryByText('編輯')).toBeNull();
			expect(screen.getByText('刪除')).toBeInTheDocument();
		});
	});

	describe('creating', () => {
		it('posts trimmed content and prepends the new comment', async () => {
			vi.mocked(createComment).mockResolvedValue(makeComment({ id: 'new', content: 'Hello' }));
			await renderPanel();

			const textarea = screen.getByPlaceholderText('輸入評論...');
			await fireEvent.input(textarea, { target: { value: '  Hello  ' } });
			await fireEvent.click(screen.getByText('發送評論'));

			await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('評論已發送'));
			expect(createComment).toHaveBeenCalledWith('doc-1', { content: 'Hello' });
			expect(screen.getByRole('heading', { name: '評論 (2)' })).toBeInTheDocument();
			expect((textarea as HTMLTextAreaElement).value).toBe('');
			const contents = screen.getAllByText(/Hello|First comment/).map((el) => el.textContent);
			expect(contents).toEqual(['Hello', 'First comment']);
		});

		it('disables sending blank comments', async () => {
			await renderPanel();

			await fireEvent.input(screen.getByPlaceholderText('輸入評論...'), {
				target: { value: '   ' }
			});

			expect(screen.getByText('發送評論').closest('button')).toBeDisabled();
		});

		it('does not duplicate a comment already added by the WebSocket broadcast', async () => {
			const created = makeComment({ id: 'new', content: 'Hello' });
			vi.mocked(createComment).mockImplementation(async () => created);
			const { component } = await renderPanel();

			component.addCommentFromWS({ ...created, author_id: '1' });
			await fireEvent.input(screen.getByPlaceholderText('輸入評論...'), {
				target: { value: 'Hello' }
			});
			await fireEvent.click(screen.getByText('發送評論'));

			await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('評論已發送'));
			expect(screen.getAllByText('Hello')).toHaveLength(1);
			expect(screen.getByRole('heading', { name: '評論 (2)' })).toBeInTheDocument();
		});

		it('reports send failures and keeps the draft', async () => {
			vi.mocked(createComment).mockRejectedValue(new Error('nope'));
			await renderPanel();

			const textarea = screen.getByPlaceholderText('輸入評論...');
			await fireEvent.input(textarea, { target: { value: 'Draft' } });
			await fireEvent.click(screen.getByText('發送評論'));

			await waitFor(() => expect(toastError).toHaveBeenCalledWith('發送評論失敗'));
			expect((textarea as HTMLTextAreaElement).value).toBe('Draft');
		});
	});

	describe('editing and deleting', () => {
		it('saves trimmed edits', async () => {
			vi.mocked(updateComment).mockResolvedValue(makeComment({ content: 'Edited' }));
			await renderPanel();

			await fireEvent.click(screen.getByText('編輯'));
			const editor = screen.getByDisplayValue('First comment');
			await fireEvent.input(editor, { target: { value: ' Edited ' } });
			await fireEvent.click(screen.getByText('儲存'));

			await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('評論已更新'));
			expect(updateComment).toHaveBeenCalledWith('doc-1', 'c1', { content: 'Edited' });
			expect(screen.getByText('Edited')).toBeInTheDocument();
			expect(screen.queryByText('儲存')).toBeNull();
		});

		it('ignores blank edits', async () => {
			await renderPanel();

			await fireEvent.click(screen.getByText('編輯'));
			await fireEvent.input(screen.getByDisplayValue('First comment'), { target: { value: '  ' } });
			await fireEvent.click(screen.getByText('儲存'));

			expect(updateComment).not.toHaveBeenCalled();
		});

		it('deletes after confirmation and updates the count', async () => {
			vi.mocked(deleteComment).mockResolvedValue({ success: true, message: 'ok' });
			await renderPanel();

			await fireEvent.click(screen.getByText('刪除'));
			const dialog = screen.getByRole('alertdialog');
			await fireEvent.click(within(dialog).getByText('刪除'));

			await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('評論已刪除'));
			expect(deleteComment).toHaveBeenCalledWith('doc-1', 'c1');
			expect(screen.queryByText('First comment')).toBeNull();
			expect(screen.getByRole('heading', { name: '評論' })).toBeInTheDocument();
		});
	});

	describe('replies', () => {
		const parent = makeComment({ reply_count: 1 });
		const reply = makeComment({
			id: 'r1',
			content: 'A reply',
			parent_id: 'c1',
			is_author: false,
			can_delete: false
		});

		beforeEach(() => {
			vi.mocked(getComments).mockResolvedValue(page([parent]));
			vi.mocked(getReplies).mockResolvedValue([reply]);
		});

		it('expands and collapses replies', async () => {
			await renderPanel();

			await fireEvent.click(screen.getByText('1 則回覆'));
			expect(await screen.findByText('A reply')).toBeInTheDocument();
			expect(getReplies).toHaveBeenCalledWith('doc-1', 'c1');

			await fireEvent.click(screen.getByText('1 則回覆'));
			await waitFor(() => expect(screen.queryByText('A reply')).toBeNull());
		});

		it('appends a submitted reply to the expanded thread', async () => {
			vi.mocked(createComment).mockResolvedValue(
				makeComment({ id: 'r2', content: 'My reply', parent_id: 'c1' })
			);
			await renderPanel();
			await fireEvent.click(screen.getByText('1 則回覆'));
			await screen.findByText('A reply');

			await fireEvent.click(screen.getByText('回覆'));
			await fireEvent.input(screen.getByPlaceholderText('輸入回覆...'), {
				target: { value: ' My reply ' }
			});
			await fireEvent.click(screen.getByText('發送'));

			await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('回覆已發送'));
			expect(createComment).toHaveBeenCalledWith('doc-1', { content: 'My reply', parent_id: 'c1' });
			expect(screen.getByText('My reply')).toBeInTheDocument();
			expect(screen.queryByPlaceholderText('輸入回覆...')).toBeNull();
		});
	});

	describe('WebSocket updates', () => {
		it('adds a top-level comment from another user with computed permissions', async () => {
			const { component } = await renderPanel();

			component.addCommentFromWS({
				id: 'ws1',
				content: 'From Bob',
				author_username: 'bob',
				author_id: '2',
				created_at: '2026-03-02T10:00:00Z',
				updated_at: '2026-03-02T10:00:00Z',
				parent_id: null,
				reply_count: 0
			});

			expect(await screen.findByText('From Bob')).toBeInTheDocument();
			expect(screen.getByRole('heading', { name: '評論 (2)' })).toBeInTheDocument();
			// bob 的評論：非作者不可編輯；非擁有者不可刪除 → 只剩自己那則的編輯/刪除
			expect(screen.getAllByText('編輯')).toHaveLength(1);
			expect(screen.getAllByText('刪除')).toHaveLength(1);
		});

		it('lets the document owner delete comments arriving over WebSocket', async () => {
			vi.mocked(getComments).mockResolvedValue(page([]));
			const { component } = await renderPanel({ isOwner: true });

			component.addCommentFromWS({
				id: 'ws1',
				content: 'From Bob',
				author_username: 'bob',
				author_id: '2',
				created_at: '2026-03-02T10:00:00Z',
				updated_at: '2026-03-02T10:00:00Z',
				parent_id: null,
				reply_count: 0
			});

			await screen.findByText('From Bob');
			expect(screen.queryByText('編輯')).toBeNull();
			expect(screen.getByText('刪除')).toBeInTheDocument();
		});

		it('ignores duplicate top-level broadcasts', async () => {
			const { component } = await renderPanel();
			const ws = {
				id: 'c1',
				content: 'First comment',
				author_username: 'alice',
				author_id: '1',
				created_at: '2026-03-01T10:00:00Z',
				updated_at: '2026-03-01T10:00:00Z',
				parent_id: null,
				reply_count: 0
			};

			component.addCommentFromWS(ws);

			await waitFor(() => expect(screen.getAllByText('First comment')).toHaveLength(1));
			expect(screen.getByRole('heading', { name: '評論 (1)' })).toBeInTheDocument();
		});

		it('increments the parent reply count for reply broadcasts', async () => {
			const { component } = await renderPanel();

			component.addCommentFromWS({
				id: 'r9',
				content: 'reply',
				author_username: 'bob',
				author_id: '2',
				created_at: '2026-03-02T10:00:00Z',
				updated_at: '2026-03-02T10:00:00Z',
				parent_id: 'c1',
				reply_count: 0
			});

			expect(await screen.findByText('1 則回覆')).toBeInTheDocument();
			expect(screen.getByRole('heading', { name: '評論 (1)' })).toBeInTheDocument();
		});

		it('applies content updates', async () => {
			const { component } = await renderPanel();

			component.updateCommentFromWS('c1', 'Changed remotely', '2026-03-03T10:00:00Z');

			expect(await screen.findByText('Changed remotely')).toBeInTheDocument();
		});

		it('removes top-level comments once', async () => {
			vi.mocked(getComments).mockResolvedValue(
				page([makeComment(), makeComment({ id: 'c2', content: 'Second' })])
			);
			const { component } = await renderPanel();

			component.removeCommentFromWS('c1', null);
			component.removeCommentFromWS('c1', null);

			await waitFor(() => expect(screen.queryByText('First comment')).toBeNull());
			expect(screen.getByRole('heading', { name: '評論 (1)' })).toBeInTheDocument();
		});

		it('removes an expanded reply and decrements the count once', async () => {
			vi.mocked(getComments).mockResolvedValue(page([makeComment({ reply_count: 2 })]));
			vi.mocked(getReplies).mockResolvedValue([
				makeComment({ id: 'r1', content: 'Reply one', parent_id: 'c1' }),
				makeComment({ id: 'r2', content: 'Reply two', parent_id: 'c1' })
			]);
			const { component } = await renderPanel();
			await fireEvent.click(screen.getByText('2 則回覆'));
			await screen.findByText('Reply one');

			component.removeCommentFromWS('r1', 'c1');
			component.removeCommentFromWS('r1', 'c1');

			await waitFor(() => expect(screen.queryByText('Reply one')).toBeNull());
			expect(screen.getByText('Reply two')).toBeInTheDocument();
			expect(screen.getByText('1 則回覆')).toBeInTheDocument();
		});
	});
});
