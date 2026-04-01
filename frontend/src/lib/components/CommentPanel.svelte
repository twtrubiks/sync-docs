<script lang="ts">
	import { browser } from '$app/environment';
	import {
		getComments,
		createComment,
		updateComment,
		deleteComment,
		type Comment,
		type CommentCreatePayload
	} from '$lib/api/comments';
	import { toastSuccess, toastError } from '$lib/toast';
	import { X, MessageSquare, Send, PenLine, Trash2, MessageCircle } from '@lucide/svelte';
	import ConfirmDialog from './ConfirmDialog.svelte';

	interface Props {
		documentId: string;
		isOpen: boolean;
		canWrite: boolean;
		currentUserId: string | null; // 當前用戶 ID（字串格式，與 WebSocket 一致）
		isOwner: boolean; // 當前用戶是否是文件擁有者（與現有頁面命名一致）
	}

	let { documentId, isOpen = $bindable(false), canWrite, currentUserId, isOwner }: Props = $props();

	let comments = $state<Comment[]>([]);
	let loading = $state(false);
	let loadingMore = $state(false);
	let newCommentContent = $state('');
	let submitting = $state(false);
	let editingId = $state<string | null>(null);
	let editContent = $state('');
	let currentPage = $state(1);
	let totalPages = $state(1);
	let hasMore = $derived(currentPage < totalPages);

	// ========== 載入評論（第一頁） ==========
	async function loadComments() {
		if (!browser) return;

		loading = true;
		currentPage = 1;
		try {
			const result = await getComments(documentId, 1);
			comments = result.comments;
			currentPage = result.page;
			totalPages = result.total_pages;
		} catch (error) {
			toastError('載入評論失敗');
			console.error('Failed to load comments:', error);
		} finally {
			loading = false;
		}
	}

	// ========== 載入更多評論 ==========
	async function loadMoreComments() {
		if (!browser || loadingMore || !hasMore) return;

		loadingMore = true;
		try {
			const result = await getComments(documentId, currentPage + 1);
			comments = [...comments, ...result.comments];
			currentPage = result.page;
			totalPages = result.total_pages;
		} catch (error) {
			toastError('載入更多評論失敗');
			console.error('Failed to load more comments:', error);
		} finally {
			loadingMore = false;
		}
	}

	// ========== 創建評論 ==========
	async function handleSubmit() {
		if (!newCommentContent.trim() || submitting) return;

		submitting = true;
		try {
			const payload: CommentCreatePayload = { content: newCommentContent.trim() };
			const newComment = await createComment(documentId, payload);
			// 檢查是否已存在（WebSocket 可能已先收到廣播）
			if (!comments.find((c) => c.id === newComment.id)) {
				comments = [newComment, ...comments];
			}
			newCommentContent = '';
			toastSuccess('評論已發送');
		} catch (error) {
			toastError('發送評論失敗');
			console.error('Failed to create comment:', error);
		} finally {
			submitting = false;
		}
	}

	// ========== 編輯評論 ==========
	function startEdit(comment: Comment) {
		editingId = comment.id;
		editContent = comment.content;
	}

	function cancelEdit() {
		editingId = null;
		editContent = '';
	}

	async function saveEdit(commentId: string) {
		if (!editContent.trim()) return;

		try {
			const updated = await updateComment(documentId, commentId, { content: editContent.trim() });
			comments = comments.map((c) => (c.id === commentId ? updated : c));
			cancelEdit();
			toastSuccess('評論已更新');
		} catch (error) {
			toastError('更新評論失敗');
			console.error('Failed to update comment:', error);
		}
	}

	// ========== 刪除評論 ==========
	let showDeleteConfirm = $state(false);
	let pendingDeleteCommentId = $state<string | null>(null);

	function handleDelete(commentId: string) {
		pendingDeleteCommentId = commentId;
		showDeleteConfirm = true;
	}

	async function confirmDeleteComment() {
		if (!pendingDeleteCommentId) return;
		const commentId = pendingDeleteCommentId;
		pendingDeleteCommentId = null;

		try {
			await deleteComment(documentId, commentId);
			comments = comments.filter((c) => c.id !== commentId);
			toastSuccess('評論已刪除');
		} catch (error) {
			toastError('刪除評論失敗');
			console.error('Failed to delete comment:', error);
		}
	}

	// ========== WebSocket 更新方法（供外部調用） ==========

	// WebSocket 傳來的評論數據（不包含 is_author 和 can_delete）
	interface WSComment {
		id: string;
		content: string;
		author_username: string;
		author_id: string; // 字串格式（後端 str(user.id)）
		created_at: string;
		updated_at: string;
		parent_id: string | null;
		reply_count: number;
	}

	export function addCommentFromWS(wsComment: WSComment) {
		// 檢查是否已存在（避免重複）
		if (comments.find((c) => c.id === wsComment.id)) return;

		// 根據當前用戶計算權限（字串比較）
		const isAuthor = wsComment.author_id === currentUserId;

		// 從 WSComment 提取需要的欄位，排除 author_id（Comment 介面沒有這個欄位）
		const { author_id: _, ...rest } = wsComment;
		const comment: Comment = {
			...rest,
			is_author: isAuthor,
			can_delete: isAuthor || isOwner
		};

		comments = [comment, ...comments];
	}

	export function updateCommentFromWS(commentId: string, content: string, updated_at: string) {
		comments = comments.map((c) => (c.id === commentId ? { ...c, content, updated_at } : c));
	}

	export function removeCommentFromWS(commentId: string) {
		comments = comments.filter((c) => c.id !== commentId);
	}

	// ========== 格式化時間 ==========
	function formatTime(dateStr: string): string {
		const date = new Date(dateStr);
		return date.toLocaleString('zh-TW', {
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	// ========== 關閉面板 ==========
	function closePanel() {
		isOpen = false;
	}

	// ========== 監聽 isOpen 變化載入評論 ==========
	$effect(() => {
		if (isOpen && browser) {
			loadComments();
		}
	});
</script>

{#if isOpen}
	<!-- 背景遮罩 -->
	<button
		type="button"
		class="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
		onclick={closePanel}
		onkeydown={(e) => e.key === 'Escape' && closePanel()}
		aria-label="關閉評論面板"
	></button>

	<!-- 側邊面板 -->
	<div
		class="border-primary-200 fixed top-0 right-0 z-50 flex h-full w-full flex-col border-l bg-white shadow-2xl sm:w-96"
	>
		<!-- 標題 -->
		<div class="border-primary-200 flex items-center justify-between border-b p-4">
			<div class="flex items-center gap-2">
				<MessageSquare size={20} class="text-primary-500" />
				<h2 class="text-primary-900 text-lg font-semibold">評論</h2>
			</div>
			<button
				type="button"
				class="text-primary-400 hover:bg-primary-100 hover:text-primary-600 cursor-pointer rounded-lg p-1.5 transition-colors"
				onclick={closePanel}
				aria-label="關閉"
			>
				<X size={20} />
			</button>
		</div>

		<!-- 新評論輸入區（僅有寫入權限時顯示） -->
		{#if canWrite}
			<div class="border-primary-200 border-b p-4">
				<textarea
					class="border-primary-300 focus:border-primary-500 focus:ring-primary-500/20 w-full resize-none rounded-lg border p-3 text-sm transition-all duration-150 focus:ring-2 focus:outline-none"
					rows="3"
					placeholder="輸入評論..."
					bind:value={newCommentContent}
				></textarea>
				<button
					type="button"
					class="bg-primary-600 hover:bg-primary-700 mt-3 flex w-full cursor-pointer items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium text-white
							 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
					onclick={handleSubmit}
					disabled={submitting || !newCommentContent.trim()}
				>
					{#if submitting}
						<span
							class="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"
						></span>
						<span>發送中...</span>
					{:else}
						<Send size={16} />
						<span>發送評論</span>
					{/if}
				</button>
			</div>
		{/if}

		<!-- 評論列表 -->
		<div class="flex-1 overflow-y-auto">
			{#if loading}
				<div class="flex items-center justify-center py-12">
					<div
						class="border-primary-200 border-t-primary-600 h-6 w-6 animate-spin rounded-full border-2"
					></div>
					<span class="text-primary-500 ml-2">載入中...</span>
				</div>
			{:else if comments.length === 0}
				<div class="py-12 text-center">
					<MessageCircle size={40} class="text-primary-300 mx-auto mb-3" />
					<p class="text-primary-500">尚無評論</p>
				</div>
			{:else}
				<div class="divide-primary-100 divide-y">
					{#each comments as comment (comment.id)}
						<div class="hover:bg-primary-50/50 p-4 transition-colors">
							<!-- 評論頭部 -->
							<div class="flex items-center justify-between">
								<span class="text-primary-800 text-sm font-medium">{comment.author_username}</span>
								<span class="text-primary-500 text-xs">{formatTime(comment.created_at)}</span>
							</div>

							<!-- 評論內容 -->
							{#if editingId === comment.id}
								<textarea
									class="border-primary-300 focus:border-primary-500 mt-2 w-full rounded-lg border p-2 text-sm focus:outline-none"
									rows="2"
									bind:value={editContent}
								></textarea>
								<div class="mt-2 flex gap-2">
									<button
										type="button"
										class="bg-primary-600 hover:bg-primary-700 cursor-pointer rounded-lg px-3 py-1.5 text-xs font-medium text-white"
										onclick={() => saveEdit(comment.id)}
									>
										儲存
									</button>
									<button
										type="button"
										class="bg-primary-100 text-primary-700 hover:bg-primary-200 cursor-pointer rounded-lg px-3 py-1.5 text-xs font-medium"
										onclick={cancelEdit}
									>
										取消
									</button>
								</div>
							{:else}
								<p class="text-primary-700 mt-2 text-sm whitespace-pre-wrap">{comment.content}</p>

								<!-- 操作按鈕 -->
								{#if comment.is_author || comment.can_delete}
									<div class="mt-3 flex gap-3">
										{#if comment.is_author}
											<button
												type="button"
												class="text-primary-500 hover:text-primary-700 flex cursor-pointer items-center gap-1 text-xs transition-colors"
												onclick={() => startEdit(comment)}
											>
												<PenLine size={12} />
												編輯
											</button>
										{/if}
										{#if comment.can_delete}
											<button
												type="button"
												class="text-primary-500 hover:text-danger flex cursor-pointer items-center gap-1 text-xs transition-colors"
												onclick={() => handleDelete(comment.id)}
											>
												<Trash2 size={12} />
												刪除
											</button>
										{/if}
									</div>
								{/if}

								<!-- 回覆數量 -->
								{#if comment.reply_count > 0}
									<div class="text-primary-500 mt-2 flex items-center gap-1 text-xs">
										<MessageCircle size={12} />
										{comment.reply_count} 則回覆
									</div>
								{/if}
							{/if}
						</div>
					{/each}
				</div>
				{#if hasMore}
					<div class="p-4 text-center">
						<button
							type="button"
							class="text-primary-600 hover:bg-primary-100 cursor-pointer rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50"
							onclick={loadMoreComments}
							disabled={loadingMore}
						>
							{#if loadingMore}
								<span class="inline-flex items-center gap-2">
									<span
										class="border-primary-300 border-t-primary-600 h-4 w-4 animate-spin rounded-full border-2"
									></span>
									載入中...
								</span>
							{:else}
								載入更多評論
							{/if}
						</button>
					</div>
				{/if}
			{/if}
		</div>
	</div>
{/if}

<ConfirmDialog
	bind:isOpen={showDeleteConfirm}
	title="刪除評論"
	message="確定要刪除這則評論嗎？"
	confirmText="刪除"
	variant="danger"
	onConfirm={confirmDeleteComment}
	onCancel={() => {
		pendingDeleteCommentId = null;
	}}
/>
