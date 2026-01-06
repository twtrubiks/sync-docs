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
	import { toast } from '@zerodevx/svelte-toast';

	interface Props {
		documentId: string;
		isOpen: boolean;
		canWrite: boolean;
		currentUserId: string | null; // 當前用戶 ID（字串格式，與 WebSocket 一致）
		isOwner: boolean; // 當前用戶是否是文件擁有者（與現有頁面命名一致）
	}

	let { documentId, isOpen = $bindable(false), canWrite, currentUserId, isOwner }: Props =
		$props();

	let comments = $state<Comment[]>([]);
	let loading = $state(false);
	let newCommentContent = $state('');
	let submitting = $state(false);
	let editingId = $state<string | null>(null);
	let editContent = $state('');

	// ========== 載入評論 ==========
	async function loadComments() {
		if (!browser) return;

		loading = true;
		try {
			const result = await getComments(documentId);
			comments = result.comments;
		} catch (error) {
			toast.push('載入評論失敗', { theme: { '--toastBackground': '#ef4444' } });
			console.error('Failed to load comments:', error);
		} finally {
			loading = false;
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
			toast.push('評論已發送', { theme: { '--toastBackground': '#22c55e' } });
		} catch (error) {
			toast.push('發送評論失敗', { theme: { '--toastBackground': '#ef4444' } });
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
			toast.push('評論已更新', { theme: { '--toastBackground': '#22c55e' } });
		} catch (error) {
			toast.push('更新評論失敗', { theme: { '--toastBackground': '#ef4444' } });
			console.error('Failed to update comment:', error);
		}
	}

	// ========== 刪除評論 ==========
	async function handleDelete(commentId: string) {
		const confirmed = confirm('確定要刪除這則評論嗎？');
		if (!confirmed) return;

		try {
			await deleteComment(documentId, commentId);
			comments = comments.filter((c) => c.id !== commentId);
			toast.push('評論已刪除', { theme: { '--toastBackground': '#22c55e' } });
		} catch (error) {
			toast.push('刪除評論失敗', { theme: { '--toastBackground': '#ef4444' } });
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
		const { author_id, ...rest } = wsComment;
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
		class="fixed inset-0 z-40 bg-black/50"
		onclick={closePanel}
		onkeydown={(e) => e.key === 'Escape' && closePanel()}
		aria-label="關閉評論面板"
	></button>

	<!-- 側邊面板 -->
	<div class="fixed top-0 right-0 z-50 flex h-full w-96 flex-col bg-white shadow-xl">
		<!-- 標題 -->
		<div class="flex items-center justify-between border-b p-4">
			<h2 class="text-lg font-semibold">評論</h2>
			<button
				type="button"
				class="text-gray-500 hover:text-gray-700"
				onclick={closePanel}
				aria-label="關閉"
			>
				<svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M6 18L18 6M6 6l12 12"
					/>
				</svg>
			</button>
		</div>

		<!-- 新評論輸入區（僅有寫入權限時顯示） -->
		{#if canWrite}
			<div class="border-b p-4">
				<textarea
					class="w-full rounded-lg border p-2 text-sm focus:border-blue-500 focus:outline-none"
					rows="3"
					placeholder="輸入評論..."
					bind:value={newCommentContent}
				></textarea>
				<button
					type="button"
					class="mt-2 w-full rounded-lg bg-blue-600 px-4 py-2 text-sm text-white transition-colors
							 hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
					onclick={handleSubmit}
					disabled={submitting || !newCommentContent.trim()}
				>
					{submitting ? '發送中...' : '發送評論'}
				</button>
			</div>
		{/if}

		<!-- 評論列表 -->
		<div class="flex-1 overflow-y-auto">
			{#if loading}
				<div class="p-4 text-center text-gray-500">載入中...</div>
			{:else if comments.length === 0}
				<div class="p-4 text-center text-gray-500">尚無評論</div>
			{:else}
				<div class="divide-y">
					{#each comments as comment (comment.id)}
						<div class="p-4">
							<!-- 評論頭部 -->
							<div class="flex items-center justify-between">
								<span class="text-sm font-medium">{comment.author_username}</span>
								<span class="text-xs text-gray-500">{formatTime(comment.created_at)}</span>
							</div>

							<!-- 評論內容 -->
							{#if editingId === comment.id}
								<textarea
									class="mt-2 w-full rounded border p-2 text-sm"
									rows="2"
									bind:value={editContent}
								></textarea>
								<div class="mt-2 flex gap-2">
									<button
										type="button"
										class="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-700"
										onclick={() => saveEdit(comment.id)}
									>
										儲存
									</button>
									<button
										type="button"
										class="rounded bg-gray-300 px-3 py-1 text-xs hover:bg-gray-400"
										onclick={cancelEdit}
									>
										取消
									</button>
								</div>
							{:else}
								<p class="mt-1 whitespace-pre-wrap text-sm text-gray-700">{comment.content}</p>

								<!-- 操作按鈕 -->
								{#if comment.is_author || comment.can_delete}
									<div class="mt-2 flex gap-2">
										{#if comment.is_author}
											<button
												type="button"
												class="text-xs text-blue-600 hover:underline"
												onclick={() => startEdit(comment)}
											>
												編輯
											</button>
										{/if}
										{#if comment.can_delete}
											<button
												type="button"
												class="text-xs text-red-600 hover:underline"
												onclick={() => handleDelete(comment.id)}
											>
												刪除
											</button>
										{/if}
									</div>
								{/if}

								<!-- 回覆數量 -->
								{#if comment.reply_count > 0}
									<div class="mt-2 text-xs text-gray-500">
										{comment.reply_count} 則回覆
									</div>
								{/if}
							{/if}
						</div>
					{/each}
				</div>
			{/if}
		</div>
	</div>
{/if}
