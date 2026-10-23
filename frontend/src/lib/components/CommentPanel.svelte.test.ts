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

		it('shows a loading state until the first page arrives', async () => {
			vi.mocked(getComments).mockReturnValue(new Promise(() => {}));

			render(CommentPanel, { props: defaultProps });

			expect(await screen.findByText('載入中...')).toBeInTheDocument();
			expect(screen.queryByText('尚無評論')).toBeNull();
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

			const send = screen.getByText('發送評論').closest('button')!;
			expect(send).toBeDisabled();
			await fireEvent.click(send);
			expect(createComment).not.toHaveBeenCalled();
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

	describe('closing', () => {
		it.each([
			['the close button', () => fireEvent.click(screen.getByLabelText('關閉'))],
			['the backdrop', () => fireEvent.click(screen.getByLabelText('關閉評論面板'))],
			[
				'Escape on the backdrop',
				() => fireEvent.keyDown(screen.getByLabelText('關閉評論面板'), { key: 'Escape' })
			]
		])('closes with %s', async (_label, close) => {
			await renderPanel();

			await close();

			expect(screen.queryByRole('heading', { name: /評論/ })).toBeNull();
		});

		it('ignores other keys on the backdrop', async () => {
			await renderPanel();

			await fireEvent.keyDown(screen.getByLabelText('關閉評論面板'), { key: 'Enter' });

			expect(screen.getByRole('heading', { name: /評論/ })).toBeInTheDocument();
		});
	});

	describe('in-flight requests', () => {
		function deferred<T>() {
			let resolve!: (value: T) => void;
			let reject!: (reason: unknown) => void;
			const promise = new Promise<T>((res, rej) => {
				resolve = res;
				reject = rej;
			});
			return { promise, resolve, reject };
		}

		it('disables load more while loading and re-enables it for the next page', async () => {
			const next = deferred<ReturnType<typeof page>>();
			vi.mocked(getComments)
				.mockResolvedValueOnce(page([makeComment()], { page: 1, total_pages: 3, total: 3 }))
				.mockReturnValueOnce(next.promise);
			await renderPanel();

			await fireEvent.click(screen.getByText('載入更多評論'));
			const button = screen.getByText('載入中...').closest('button')!;
			expect(button).toBeDisabled();
			await fireEvent.click(button); // 載入中再點一次不應重複請求同一頁
			expect(getComments).toHaveBeenCalledTimes(2);

			next.resolve(
				page([makeComment({ id: 'c2', content: 'Older' })], { page: 2, total_pages: 3, total: 3 })
			);
			await screen.findByText('Older');
			expect(screen.getByText('載入更多評論').closest('button')).not.toBeDisabled();
		});

		it('reports load more failures and lets the user retry', async () => {
			vi.mocked(getComments)
				.mockResolvedValueOnce(page([makeComment()], { page: 1, total_pages: 2, total: 2 }))
				.mockRejectedValueOnce(new Error('boom'));
			await renderPanel();

			await fireEvent.click(screen.getByText('載入更多評論'));

			await waitFor(() => expect(toastError).toHaveBeenCalledWith('載入更多評論失敗'));
			expect(screen.getByText('載入更多評論').closest('button')).not.toBeDisabled();
		});

		it('disables sending while a comment is being posted', async () => {
			const created = deferred<Comment>();
			vi.mocked(createComment).mockReturnValue(created.promise);
			await renderPanel();
			await fireEvent.input(screen.getByPlaceholderText('輸入評論...'), {
				target: { value: 'Hello' }
			});

			await fireEvent.click(screen.getByText('發送評論'));

			const sending = screen.getByText('發送中...').closest('button')!;
			expect(sending).toBeDisabled();
			await fireEvent.click(sending);
			expect(createComment).toHaveBeenCalledTimes(1);
			created.resolve(makeComment({ id: 'new', content: 'Hello' }));
			await waitFor(() => expect(screen.getByText('發送評論')).toBeInTheDocument());
		});

		it('re-enables sending after a failed post', async () => {
			vi.mocked(createComment).mockRejectedValue(new Error('nope'));
			await renderPanel();
			await fireEvent.input(screen.getByPlaceholderText('輸入評論...'), {
				target: { value: 'Draft' }
			});

			await fireEvent.click(screen.getByText('發送評論'));

			await waitFor(() => expect(toastError).toHaveBeenCalledWith('發送評論失敗'));
			expect(screen.getByText('發送評論').closest('button')).not.toBeDisabled();
		});
	});

	describe('rendering details', () => {
		it('formats timestamps in zh-TW', async () => {
			await renderPanel();

			const expected = new Date('2026-03-01T10:00:00Z').toLocaleString('zh-TW', {
				month: 'short',
				day: 'numeric',
				hour: '2-digit',
				minute: '2-digit'
			});
			expect(screen.getByText(expected)).toBeInTheDocument();
		});

		it('lets read-only authors still edit their own comments', async () => {
			vi.mocked(getComments).mockResolvedValue(
				page([makeComment({ is_author: true, can_delete: false })])
			);

			await renderPanel({ canWrite: false });

			expect(screen.getByText('編輯')).toBeInTheDocument();
			expect(screen.queryByText('回覆')).toBeNull();
		});

		it('does not offer to expand comments without replies', async () => {
			await renderPanel();

			expect(screen.queryByText(/則回覆/)).toBeNull();
		});
	});

	describe('editing state', () => {
		it('starting a reply cancels an edit in progress, and vice versa', async () => {
			vi.mocked(getComments).mockResolvedValue(
				page([makeComment(), makeComment({ id: 'c2', content: 'Second', is_author: false })])
			);
			await renderPanel();

			// 編輯中的評論不顯示操作按鈕，因此在另一則評論上開始回覆
			await fireEvent.click(screen.getByText('編輯'));
			await fireEvent.click(screen.getByText('回覆'));
			expect(screen.queryByText('儲存')).toBeNull();
			expect(screen.getByPlaceholderText('輸入回覆...')).toBeInTheDocument();

			await fireEvent.click(screen.getByText('編輯'));
			expect(screen.queryByPlaceholderText('輸入回覆...')).toBeNull();
			expect(screen.getByText('儲存')).toBeInTheDocument();
		});

		it('starts every reply with an empty draft', async () => {
			await renderPanel();

			await fireEvent.click(screen.getByText('回覆'));
			await fireEvent.input(screen.getByPlaceholderText('輸入回覆...'), {
				target: { value: 'draft' }
			});
			await fireEvent.click(screen.getByText('取消'));
			await fireEvent.click(screen.getByText('回覆'));

			expect((screen.getByPlaceholderText('輸入回覆...') as HTMLTextAreaElement).value).toBe('');
			expect(screen.getByText('發送').closest('button')).toBeDisabled();

			// 只有空白的回覆同樣不能送出
			await fireEvent.input(screen.getByPlaceholderText('輸入回覆...'), {
				target: { value: '   ' }
			});
			expect(screen.getByText('發送').closest('button')).toBeDisabled();
			await fireEvent.click(screen.getByText('發送'));
			expect(createComment).not.toHaveBeenCalled();
		});

		it('updates only the edited comment', async () => {
			vi.mocked(getComments).mockResolvedValue(
				page([makeComment(), makeComment({ id: 'c2', content: 'Second', is_author: false })])
			);
			vi.mocked(updateComment).mockResolvedValue(makeComment({ content: 'Edited' }));
			await renderPanel();

			await fireEvent.click(screen.getByText('編輯'));
			await fireEvent.input(screen.getByDisplayValue('First comment'), {
				target: { value: 'Edited' }
			});
			await fireEvent.click(screen.getByText('儲存'));

			await screen.findByText('Edited');
			expect(screen.getByText('Second')).toBeInTheDocument();
		});

		it('reports failed edits and keeps the editor open', async () => {
			vi.mocked(updateComment).mockRejectedValue(new Error('nope'));
			await renderPanel();

			await fireEvent.click(screen.getByText('編輯'));
			await fireEvent.click(screen.getByText('儲存'));

			await waitFor(() => expect(toastError).toHaveBeenCalledWith('更新評論失敗'));
			expect(screen.getByText('儲存')).toBeInTheDocument();
		});
	});

	describe('deleting details', () => {
		it('keeps the comment when the confirmation is cancelled', async () => {
			await renderPanel();

			await fireEvent.click(screen.getByText('刪除'));
			await fireEvent.click(within(screen.getByRole('alertdialog')).getByText('取消'));

			expect(deleteComment).not.toHaveBeenCalled();
			expect(screen.getByText('First comment')).toBeInTheDocument();
		});

		it('removes only the deleted comment', async () => {
			vi.mocked(getComments).mockResolvedValue(
				page([makeComment(), makeComment({ id: 'c2', content: 'Second' })])
			);
			vi.mocked(deleteComment).mockResolvedValue({ success: true, message: 'ok' });
			await renderPanel();

			await fireEvent.click(screen.getAllByText('刪除')[1]);
			await fireEvent.click(within(screen.getByRole('alertdialog')).getByText('刪除'));

			await waitFor(() => expect(screen.queryByText('Second')).toBeNull());
			expect(screen.getByText('First comment')).toBeInTheDocument();
			expect(deleteComment).toHaveBeenCalledWith('doc-1', 'c2');
		});

		it('reports failed deletions and keeps the comment', async () => {
			vi.mocked(deleteComment).mockRejectedValue(new Error('nope'));
			await renderPanel();

			await fireEvent.click(screen.getByText('刪除'));
			await fireEvent.click(within(screen.getByRole('alertdialog')).getByText('刪除'));

			await waitFor(() => expect(toastError).toHaveBeenCalledWith('刪除評論失敗'));
			expect(screen.getByText('First comment')).toBeInTheDocument();
		});

		it('deletes a reply from its thread and decrements the parent count', async () => {
			vi.mocked(getComments).mockResolvedValue(page([makeComment({ reply_count: 2 })]));
			vi.mocked(getReplies).mockResolvedValue([
				makeComment({ id: 'r1', content: 'Reply one', parent_id: 'c1' }),
				makeComment({ id: 'r2', content: 'Reply two', parent_id: 'c1', can_delete: false })
			]);
			vi.mocked(deleteComment).mockResolvedValue({ success: true, message: 'ok' });
			await renderPanel();
			await fireEvent.click(screen.getByText('2 則回覆'));
			await screen.findByText('Reply one');

			await fireEvent.click(screen.getByLabelText('刪除回覆'));
			await fireEvent.click(within(screen.getByRole('alertdialog')).getByText('刪除'));

			await waitFor(() => expect(screen.queryByText('Reply one')).toBeNull());
			expect(deleteComment).toHaveBeenCalledWith('doc-1', 'r1');
			expect(screen.getByText('Reply two')).toBeInTheDocument();
			expect(screen.getByText('1 則回覆')).toBeInTheDocument();
			// 刪除回覆不影響頂層評論總數
			expect(screen.getByRole('heading', { name: '評論 (1)' })).toBeInTheDocument();
		});
	});

	describe('reply details', () => {
		const wsReply = {
			id: 'r2',
			content: 'Live reply',
			author_username: 'bob',
			author_id: '2',
			created_at: '2026-03-02T10:00:00Z',
			updated_at: '2026-03-02T10:00:00Z',
			parent_id: 'c1',
			reply_count: 0
		};

		beforeEach(() => {
			vi.mocked(getComments).mockResolvedValue(page([makeComment({ reply_count: 1 })]));
			vi.mocked(getReplies).mockResolvedValue([
				makeComment({ id: 'r1', content: 'A reply', parent_id: 'c1' })
			]);
		});

		async function expandReplies() {
			await fireEvent.click(screen.getByText('1 則回覆'));
			await screen.findByText('A reply');
		}

		it('shows a spinner while replies load and reports failures', async () => {
			let rejectReplies!: (reason: unknown) => void;
			vi.mocked(getReplies).mockReturnValue(
				new Promise((_resolve, reject) => {
					rejectReplies = reject;
				})
			);
			await renderPanel();
			const toggle = screen.getByText('1 則回覆').closest('button')!;

			await fireEvent.click(toggle);
			expect(toggle.querySelector('.animate-spin')).not.toBeNull();

			rejectReplies(new Error('boom'));
			await waitFor(() => expect(toastError).toHaveBeenCalledWith('載入回覆失敗'));
			await waitFor(() => expect(toggle.querySelector('.animate-spin')).toBeNull());
		});

		it('adds live replies to an expanded thread once, with their time', async () => {
			const { component } = await renderPanel();
			await expandReplies();

			component.addCommentFromWS(wsReply);
			component.addCommentFromWS(wsReply);

			await screen.findByText('Live reply');
			expect(screen.getAllByText('Live reply')).toHaveLength(1);
			const time = new Date(wsReply.created_at).toLocaleString('zh-TW', {
				month: 'short',
				day: 'numeric',
				hour: '2-digit',
				minute: '2-digit'
			});
			expect(screen.getByText(time)).toBeInTheDocument();
		});

		it('does not duplicate a reply the broadcast already added', async () => {
			vi.mocked(createComment).mockResolvedValue(makeComment({ ...wsReply, is_author: true }));
			const { component } = await renderPanel();
			await expandReplies();

			component.addCommentFromWS({ ...wsReply, author_id: '1' });
			await fireEvent.click(screen.getByText('回覆'));
			await fireEvent.input(screen.getByPlaceholderText('輸入回覆...'), {
				target: { value: 'Live reply' }
			});
			await fireEvent.click(screen.getByText('發送'));

			await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('回覆已發送'));
			expect(screen.getAllByText('Live reply')).toHaveLength(1);
		});

		it('replies to a collapsed thread without expanding it', async () => {
			vi.mocked(createComment).mockResolvedValue(makeComment({ ...wsReply }));
			await renderPanel();

			await fireEvent.click(screen.getByText('回覆'));
			await fireEvent.input(screen.getByPlaceholderText('輸入回覆...'), {
				target: { value: 'Live reply' }
			});
			await fireEvent.click(screen.getByText('發送'));

			await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('回覆已發送'));
			expect(toastError).not.toHaveBeenCalled();
			expect(screen.queryByText('Live reply')).toBeNull();
		});

		it('reports failed replies and re-enables sending', async () => {
			vi.mocked(createComment).mockRejectedValue(new Error('nope'));
			await renderPanel();

			await fireEvent.click(screen.getByText('回覆'));
			await fireEvent.input(screen.getByPlaceholderText('輸入回覆...'), {
				target: { value: 'Live reply' }
			});
			await fireEvent.click(screen.getByText('發送'));

			await waitFor(() => expect(toastError).toHaveBeenCalledWith('發送回覆失敗'));
			expect(screen.getByText('發送').closest('button')).not.toBeDisabled();
			expect((screen.getByPlaceholderText('輸入回覆...') as HTMLTextAreaElement).value).toBe(
				'Live reply'
			);
		});

		it('disables the reply button while sending', async () => {
			vi.mocked(createComment).mockReturnValue(new Promise(() => {}));
			await renderPanel();

			await fireEvent.click(screen.getByText('回覆'));
			await fireEvent.input(screen.getByPlaceholderText('輸入回覆...'), {
				target: { value: 'Live reply' }
			});
			await fireEvent.click(screen.getByText('發送'));

			const send = screen.getByText('發送').closest('button')!;
			expect(send).toBeDisabled();
			await fireEvent.click(send);
			expect(createComment).toHaveBeenCalledTimes(1);
		});
	});

	describe('WebSocket details', () => {
		const base = {
			author_username: 'me',
			created_at: '2026-03-02T10:00:00Z',
			updated_at: '2026-03-02T10:00:00Z',
			reply_count: 0
		};

		it('marks broadcasts from the current user as their own', async () => {
			vi.mocked(getComments).mockResolvedValue(page([]));
			const { component } = await renderPanel();

			component.addCommentFromWS({
				...base,
				id: 'mine',
				content: 'Mine',
				author_id: '1',
				parent_id: null
			});

			await screen.findByText('Mine');
			expect(screen.getByText('編輯')).toBeInTheDocument();
			expect(screen.getByText('刪除')).toBeInTheDocument();
		});

		it('counts a reply broadcast only on its parent', async () => {
			vi.mocked(getComments).mockResolvedValue(
				page([makeComment(), makeComment({ id: 'c2', content: 'Second' })])
			);
			const { component } = await renderPanel();

			component.addCommentFromWS({
				...base,
				id: 'r1',
				content: 'reply',
				author_id: '2',
				parent_id: 'c2'
			});

			expect(await screen.findAllByText('1 則回覆')).toHaveLength(1);
		});

		it('applies updates and removals only to the targeted comment', async () => {
			vi.mocked(getComments).mockResolvedValue(
				page([makeComment(), makeComment({ id: 'c2', content: 'Second' })])
			);
			const { component } = await renderPanel();

			component.updateCommentFromWS('c2', 'Changed', '2026-03-03T10:00:00Z');
			await screen.findByText('Changed');
			expect(screen.getByText('First comment')).toBeInTheDocument();

			component.removeCommentFromWS('c2', null);
			await waitFor(() => expect(screen.queryByText('Changed')).toBeNull());
			expect(screen.getByText('First comment')).toBeInTheDocument();
		});

		it('decrements the reply count of a collapsed thread only', async () => {
			vi.mocked(getComments).mockResolvedValue(
				page([
					makeComment({ reply_count: 2 }),
					makeComment({ id: 'c2', content: 'Second', reply_count: 3 })
				])
			);
			const { component } = await renderPanel();

			component.removeCommentFromWS('r1', 'c1');

			expect(await screen.findByText('1 則回覆')).toBeInTheDocument();
			expect(screen.getByText('3 則回覆')).toBeInTheDocument();
		});
	});
});
