<script lang="ts">
	import { page } from '$app/stores';
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import QuillEditor from '$lib/components/QuillEditor.svelte';
	import VersionHistoryPanel from '$lib/components/VersionHistoryPanel.svelte';
	import AIDialog from '$lib/components/AIDialog.svelte';
	import CommentPanel from '$lib/components/CommentPanel.svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
	import { get, put, del, post, logout, refreshAccessToken, type Collaborator } from '$lib/auth';
	import { toastSuccess, toastError, toastWarning } from '$lib/toast';
	import type { QuillDelta, QuillType } from '$lib/types/quill';
	import type { PresenceUser } from '$lib/types/cursor';
	import Delta from 'quill-delta';
	import {
		FileText,
		MessageSquare,
		Sparkles,
		Clock,
		Share2,
		Trash2,
		X,
		Plus,
		UserMinus,
		TriangleAlert,
		RefreshCw
	} from '@lucide/svelte';

	// WebSocket Close Codes（與後端對應）
	const WS_CLOSE_CODES = {
		AUTH_FAILED: 4001,
		TOKEN_EXPIRED: 4002,
		PERMISSION_DENIED: 4003,
		DOCUMENT_NOT_FOUND: 4004,
		TOO_MANY_CONNECTIONS: 4005,
		INVALID_MESSAGE: 4006,
		MESSAGE_TOO_LARGE: 4007,
		RATE_LIMITED: 4008
	} as const;

	// Svelte 5: $page store auto-subscription still works
	const documentId = $page.params.document_id!;

	// Svelte 5 Runes: use $state() for reactive state
	let title = $state('');
	let content: QuillDelta = $state({ ops: [] }); // Quill's content (Delta format)
	let editor: QuillType | undefined = $state(undefined); // To hold the Quill instance
	let socket: WebSocket | null = $state(null);
	let isOwner = $state(false);
	let lastSavedTime: string | null = $state(null);
	let saveStatus: 'idle' | 'unsaved' | 'saving' | 'saved' | 'error' | 'connecting' =
		$state('connecting');
	let debounceTimeout: ReturnType<typeof setTimeout> | undefined = $state(undefined);

	// Document loading state
	let isLoading = $state(true);
	let loadError: string | null = $state(null);

	// Throttle state for WebSocket delta sending
	let pendingDelta: QuillDelta | null = $state(null);
	let throttleTimeout: ReturnType<typeof setTimeout> | undefined = $state(undefined);
	let lastSendTime = $state(0);
	const THROTTLE_INTERVAL = 150; // ms（100-200ms 範圍）

	// Reconnect state
	let reconnectAttempts = $state(0);
	let reconnectTimer: ReturnType<typeof setTimeout> | undefined = $state(undefined);
	const MAX_RECONNECT_ATTEMPTS = 5;
	const BASE_RECONNECT_DELAY = 1000; // 1s

	// Permission state (from API and WebSocket)
	let canWrite = $state(true);

	// State for sharing modal
	let showShareModal = $state(false);
	let collaborators: Collaborator[] = $state([]);
	let newCollaboratorUsername = $state('');
	let newCollaboratorPermission = $state<'read' | 'write'>('write');

	// State for remove confirmation modal
	let showRemoveConfirmModal = $state(false);
	let collaboratorToRemove: Collaborator | null = $state(null);

	// State for version history panel
	let showVersionHistory = $state(false);

	// State for comment panel
	let showCommentPanel = $state(false);
	let commentPanel: CommentPanel;

	// Cursor and Presence state
	let quillEditor: QuillEditor;
	let onlineUsers = $state<Map<string, PresenceUser>>(new Map());
	let currentUserId = $state<string | null>(null);

	// Cursor change throttle state
	let cursorThrottleTimer: ReturnType<typeof setTimeout> | null = $state(null);
	let pendingCursor: { index: number; length: number } | null = $state(null);
	const CURSOR_THROTTLE_INTERVAL = 150; // ms

	// AI Dialog state
	let showAIDialog = $state(false);
	let selectedTextForAI = $state('');
	let savedSelection = $state<{ index: number; length: number } | null>(null);
	let savedOriginalText = $state(''); // For conflict detection

	async function getCollaborators() {
		try {
			collaborators = await get(`/documents/${documentId}/collaborators/`);
		} catch (error) {
			console.error('Failed to fetch collaborators:', error);
			toastError('Could not load collaborators.');
		}
	}

	async function handleAddCollaborator() {
		if (!newCollaboratorUsername) return;
		try {
			const newCollaborator = await post(`/documents/${documentId}/collaborators/`, {
				username: newCollaboratorUsername,
				permission: newCollaboratorPermission
			});
			collaborators = [...collaborators, newCollaborator];
			newCollaboratorUsername = ''; // Clear input
			newCollaboratorPermission = 'write'; // Reset to default
			toastSuccess(`Successfully added ${newCollaborator.username} as a collaborator.`);
		} catch (error: unknown) {
			console.error('Failed to add collaborator:', error);
			const message = error instanceof Error ? error.message : 'Failed to add collaborator.';
			toastError(message);
		}
	}

	function openRemoveConfirm(collaborator: Collaborator) {
		collaboratorToRemove = collaborator;
		showRemoveConfirmModal = true;
	}

	async function confirmRemoveCollaborator() {
		if (!collaboratorToRemove) return;

		try {
			await del(`/documents/${documentId}/collaborators/${collaboratorToRemove.id}/`);
			toastSuccess('Collaborator removed.');
			collaborators = collaborators.filter((c) => c.id !== collaboratorToRemove!.id);
		} catch (error) {
			console.error('Failed to remove collaborator:', error);
			toastError('Failed to remove collaborator.');
		} finally {
			// Hide and reset
			showRemoveConfirmModal = false;
			collaboratorToRemove = null;
		}
	}

	// Svelte 5 Runes: $effect() replaces $: for side effects
	// When the modal is opened, fetch the current collaborators
	$effect(() => {
		if (showShareModal) {
			getCollaborators();
		}
	});

	// Svelte 5 Runes: $derived.by() replaces $: for complex derivations
	const statusText = $derived.by(() => {
		if (loadError) return 'Failed to load document';
		switch (saveStatus) {
			case 'connecting':
				return 'Connecting...';
			case 'unsaved':
				return 'Unsaved changes';
			case 'saving':
				return 'Saving...';
			case 'saved':
				return 'All changes saved';
			case 'error':
				return 'Error saving document';
			default: // idle
				if (lastSavedTime) {
					return `Last save at ${new Date(lastSavedTime).toLocaleTimeString()}`;
				}
				return 'Ready';
		}
	});

	/**
	 * 處理 WebSocket 錯誤
	 * 根據 close code 顯示對應的錯誤訊息並執行相應操作
	 */
	async function handleWsError(code: number, message?: string) {
		switch (code) {
			case WS_CLOSE_CODES.TOKEN_EXPIRED: {
				// 嘗試用 refresh token 換取新的 access token，成功則自動重連
				const refreshed = await refreshAccessToken();
				if (refreshed) {
					console.log('Token refreshed, reconnecting WebSocket...');
					toastSuccess('Session refreshed.');
					connectWebSocket();
					return;
				}
				// Refresh 也失敗，登出
				toastError('Session expired. Please login again.');
				logout();
				goto('/login');
				break;
			}
			case WS_CLOSE_CODES.AUTH_FAILED:
				toastError('Session expired. Please login again.');
				logout();
				goto('/login');
				break;
			case WS_CLOSE_CODES.PERMISSION_DENIED:
				toastError(message || 'You do not have permission to access this document.');
				goto('/dashboard');
				break;
			case WS_CLOSE_CODES.DOCUMENT_NOT_FOUND:
				toastError('Document not found.');
				goto('/dashboard');
				break;
			case WS_CLOSE_CODES.TOO_MANY_CONNECTIONS:
				toastError('Too many open tabs. Please close some and refresh.');
				break;
			case WS_CLOSE_CODES.RATE_LIMITED:
				toastWarning('Sending too fast. Please slow down.');
				break;
			default:
				toastError(message || 'Connection lost. Please refresh the page.');
		}
	}

	/**
	 * 計算重連延遲（指數退避 + 隨機抖動）
	 * 1s → 2s → 4s → 8s → 16s（上限 30s）
	 */
	function getReconnectDelay(): number {
		const delay = Math.min(BASE_RECONNECT_DELAY * 2 ** reconnectAttempts, 30000);
		return delay + delay * 0.5 * Math.random();
	}

	/**
	 * 建立 WebSocket 連線（初始連線與重連共用）
	 */
	function connectWebSocket() {
		// Guard: 清理可能仍開啟的舊連線
		if (socket) {
			socket.onclose = null;
			socket.close();
			socket = null;
		}

		const token = localStorage.getItem('access_token');
		if (!token) {
			console.error('No auth token found, WebSocket connection aborted.');
			saveStatus = 'error';
			return;
		}
		const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
		// 使用 subprotocol 傳遞 token，而非 URL query string（更安全）
		const wsUrl = `${wsProtocol}//localhost:8000/ws/docs/${documentId}/`;
		socket = new WebSocket(wsUrl, [`access_token.${token}`]);

		socket.onopen = () => {
			console.log('WebSocket connection established');
			if (reconnectAttempts > 0) {
				toastSuccess('Connection restored.');
			}
			reconnectAttempts = 0;
			saveStatus = 'idle';
		};

		socket.onmessage = (event) => {
			const data = JSON.parse(event.data);

			switch (data.type) {
				case 'connection_success':
					// Update permission from WebSocket connection
					canWrite = data.can_write;
					currentUserId = data.user_id;
					console.log(`WebSocket connected, can_write: ${canWrite}, user_id: ${currentUserId}`);
					break;
				case 'doc_update':
					if (data.delta && editor) {
						editor.updateContents(data.delta, 'silent');
					}
					break;
				case 'doc_saved':
					if (data.updated_at) {
						lastSavedTime = data.updated_at;
						if (saveStatus === 'saving') {
							saveStatus = 'saved';
							setTimeout(() => {
								if (saveStatus === 'saved') saveStatus = 'idle';
							}, 2000);
						}
					}
					break;
				case 'cursor_move':
					// 更新其他用戶的游標
					quillEditor?.setCursor(data.user_id, data.username, data.color, data.cursor);
					break;
				case 'user_join':
					// 用戶加入
					onlineUsers.set(data.user_id, {
						user_id: data.user_id,
						username: data.username,
						color: data.color
					});
					onlineUsers = new Map(onlineUsers); // Svelte 5: 創建新 Map 觸發響應式
					break;
				case 'user_leave':
					// 用戶離開
					onlineUsers.delete(data.user_id);
					onlineUsers = new Map(onlineUsers); // Svelte 5: 創建新 Map 觸發響應式
					quillEditor?.removeCursor(data.user_id);
					break;
				case 'presence_sync': {
					// 同步在線用戶列表
					const newMap = new Map<string, PresenceUser>();
					for (const user of data.users) {
						newMap.set(user.user_id, {
							user_id: user.user_id,
							username: user.username,
							color: user.color
						});
					}
					onlineUsers = newMap; // Svelte 5: 創建新 Map 觸發響應式
					break;
				}
				case 'connection_error':
					// 連接錯誤會在 onclose 之前收到，記錄到 console
					console.warn('WebSocket connection error:', data.error_code, data.message);
					break;
				case 'error':
					// 運行時錯誤（如 RATE_LIMITED, READ_ONLY）- 連接保持
					if (data.error_code === 'RATE_LIMITED' && data.retry_after) {
						toastWarning(`Too fast! Wait ${Math.ceil(data.retry_after)}s`);
					} else if (data.error_code === 'READ_ONLY') {
						toastWarning('You have read-only access to this document.');
					} else {
						toastError(data.message || 'An error occurred.');
					}
					break;
				// Comment events
				case 'comment_add':
					commentPanel?.addCommentFromWS(data.comment);
					break;
				case 'comment_update':
					commentPanel?.updateCommentFromWS(data.comment_id, data.content, data.updated_at);
					break;
				case 'comment_delete':
					commentPanel?.removeCommentFromWS(data.comment_id);
					break;
			}
		};

		socket.onclose = (event) => {
			console.log('WebSocket closed:', event.code, event.reason);
			socket = null;

			// 正常關閉或離開頁面
			if (event.code === 1000 || event.code === 1001) return;

			// Token 過期：嘗試刷新後重連（由 handleWsError 內部處理）
			if (event.code === WS_CLOSE_CODES.TOKEN_EXPIRED) {
				handleWsError(event.code, event.reason);
				return;
			}

			// 永久性錯誤（後端主動關閉）
			if (event.code >= 4001 && event.code <= 4008) {
				saveStatus = 'error';
				handleWsError(event.code, event.reason);
				return;
			}

			// 暫時性錯誤 → 嘗試自動重連
			if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
				const delay = getReconnectDelay();
				console.log(
					`Reconnecting in ${Math.round(delay)}ms (attempt ${reconnectAttempts + 1}/${MAX_RECONNECT_ATTEMPTS})...`
				);
				saveStatus = 'connecting';
				clearTimeout(reconnectTimer);
				reconnectTimer = setTimeout(() => {
					reconnectAttempts++;
					connectWebSocket();
				}, delay);
			} else {
				saveStatus = 'error';
				toastError('Connection lost. Please refresh the page.');
			}
		};

		socket.onerror = (error) => {
			console.error('WebSocket error:', error);
		};
	}

	async function loadDocument() {
		clearTimeout(reconnectTimer); // Prevent stale auto-reconnect from firing
		isLoading = true;
		loadError = null;
		saveStatus = 'connecting';
		try {
			const doc = await get(`/documents/${documentId}/`);
			title = doc.title;
			isOwner = doc.is_owner === true; // Strict check
			canWrite = doc.can_write !== false; // Get initial permission from API
			lastSavedTime = doc.updated_at;
			if (content.ops.length === 0) {
				content = doc.content || { ops: [] };
			}

			connectWebSocket();
		} catch (error) {
			console.error('Failed to fetch document:', error);
			const message = error instanceof Error ? error.message : 'Failed to load document.';
			loadError = message;
			saveStatus = 'error';
			toastError(message);
		} finally {
			isLoading = false;
		}
	}

	onMount(() => {
		loadDocument();
	});

	const debouncedSave = () => {
		clearTimeout(debounceTimeout);
		saveStatus = 'unsaved';
		debounceTimeout = setTimeout(async () => {
			saveStatus = 'saving';
			try {
				// The content is sent via WebSocket, here we just save the title.
				// The backend consumer will save the latest content.
				await put(`/documents/${documentId}/`, { title, content });
				// The backend will broadcast 'doc_saved', which updates the status.
			} catch (error) {
				console.error('Failed to save document:', error);
				saveStatus = 'error';
				toastError('Failed to save document.');
			}
		}, 1500);
	};

	// Send pending delta via WebSocket (used by throttle mechanism)
	function sendPendingDelta() {
		if (!pendingDelta) return;
		if (socket && socket.readyState === WebSocket.OPEN) {
			socket.send(JSON.stringify({ delta: pendingDelta }));
		}
		pendingDelta = null;
		lastSendTime = Date.now();
	}

	let showDeleteConfirm = $state(false);

	function handleDelete() {
		showDeleteConfirm = true;
	}

	async function confirmDelete() {
		try {
			await del(`/documents/${documentId}/`);
			toastSuccess('文件已成功刪除');
			await goto('/dashboard');
		} catch (error) {
			console.error('Failed to delete document:', error);
			toastError('刪除文件失敗');
		}
	}

	// Svelte 5: Updated handler signature for callback prop (no more CustomEvent)
	// Uses throttle mechanism to limit WebSocket message frequency
	function handleContentChange(detail: { delta: QuillDelta; source: string }) {
		const { delta, source } = detail;
		if (source !== 'user') return;

		// Accumulate delta using Quill Delta's compose method
		if (pendingDelta) {
			const d1 = new Delta(pendingDelta.ops);
			const d2 = new Delta(delta.ops);
			pendingDelta = { ops: d1.compose(d2).ops };
		} else {
			pendingDelta = delta;
		}

		const now = Date.now();
		const timeSinceLastSend = now - lastSendTime;

		if (timeSinceLastSend >= THROTTLE_INTERVAL) {
			// Enough time has passed, send immediately
			sendPendingDelta();
		} else {
			// Schedule send for trailing edge
			clearTimeout(throttleTimeout);
			throttleTimeout = setTimeout(sendPendingDelta, THROTTLE_INTERVAL - timeSinceLastSend);
		}

		// The `content` variable is already updated by the `bind:value` directive.
		// We just need to trigger the save.
		debouncedSave();
	}

	// 游標變化處理（Trailing Edge Throttle）
	function handleSelectionChange(range: { index: number; length: number } | null) {
		if (!range || !socket || socket.readyState !== WebSocket.OPEN || !canWrite) return;

		// 記錄最新游標位置
		pendingCursor = range;

		// Trailing edge throttle：等待後發送最新值
		if (cursorThrottleTimer) return;

		cursorThrottleTimer = setTimeout(() => {
			// 重新檢查 ws 狀態
			if (pendingCursor && socket && socket.readyState === WebSocket.OPEN) {
				socket.send(
					JSON.stringify({
						type: 'cursor_move',
						index: pendingCursor.index,
						length: pendingCursor.length
					})
				);
				pendingCursor = null;
			}
			cursorThrottleTimer = null;
		}, CURSOR_THROTTLE_INTERVAL);
	}

	// Open AI Dialog
	function openAIDialog() {
		if (!editor) return;

		const selection = editor.getSelection();
		if (!selection || selection.length === 0) {
			toastWarning('Please select text first');
			return;
		}

		// Save selection range and original text
		savedSelection = { index: selection.index, length: selection.length };
		savedOriginalText = editor.getText(selection.index, selection.length);
		selectedTextForAI = savedOriginalText;
		showAIDialog = true;
	}

	// Apply AI result
	function applyAIResult(newText: string) {
		if (!editor || !savedSelection) return;

		// Conflict detection: check if original text was modified by others
		const currentText = editor.getText(savedSelection.index, savedSelection.length);
		if (currentText !== savedOriginalText) {
			toastWarning('Text was modified. Please reselect.');
			savedSelection = null;
			savedOriginalText = '';
			return;
		}

		// Get original formatting, preserve it when applying result
		const formats = editor.getFormat(savedSelection.index, savedSelection.length);

		// Replace text using saved selection (preserve original formatting)
		editor.deleteText(savedSelection.index, savedSelection.length, 'user');
		editor.insertText(savedSelection.index, newText, formats, 'user');

		// Clear saved state
		savedSelection = null;
		savedOriginalText = '';

		// Note: Using 'user' as source will trigger text-change event
		// Changes will be synced to other collaborators via existing WebSocket mechanism
	}

	// 還原版本後重新載入文件
	async function handleVersionRestore() {
		try {
			const doc = await get(`/documents/${documentId}/`);
			title = doc.title;
			content = doc.content || { ops: [] };
			// 更新編輯器內容
			if (editor) {
				editor.setContents(content.ops, 'silent');
			}
			lastSavedTime = doc.updated_at;
			saveStatus = 'saved';
			setTimeout(() => {
				if (saveStatus === 'saved') saveStatus = 'idle';
			}, 2000);
		} catch (error) {
			console.error('Failed to reload document after restore:', error);
			toastError('Failed to reload document.');
		}
	}

	onDestroy(() => {
		// Send any pending delta before closing
		if (pendingDelta && socket?.readyState === WebSocket.OPEN) {
			socket.send(JSON.stringify({ delta: pendingDelta }));
		}

		clearTimeout(reconnectTimer);
		if (socket) {
			// Prevent the onclose handler from firing when we navigate away
			socket.onclose = null;
			socket.close();
		}
		clearTimeout(debounceTimeout);
		clearTimeout(throttleTimeout);
		if (cursorThrottleTimer) {
			clearTimeout(cursorThrottleTimer);
		}
	});
</script>

<div class="page-container">
	<header class="header">
		<div class="header-left">
			<a
				href="/dashboard"
				class="logo-link"
				title="Back to Dashboard"
				aria-label="Back to Dashboard"
			>
				<FileText size={24} class="sm:hidden" />
				<FileText size={28} class="hidden sm:block" />
			</a>
			<div class="doc-info">
				<div class="title-row">
					<input
						type="text"
						bind:value={title}
						oninput={debouncedSave}
						class="doc-title-input"
						placeholder="Untitled Document"
						disabled={!canWrite}
					/>
					{#if !canWrite}
						<span class="read-only-badge">View Only</span>
					{/if}
				</div>
				<div class="doc-status">{statusText}</div>
			</div>
		</div>
		{#if !isLoading && !loadError}
			<div class="header-right">
				<!-- 在線用戶頭像 -->
				<div class="online-users">
					{#each [...onlineUsers.entries()] as [userId, user] (userId)}
						{#if userId !== currentUserId}
							<div class="user-avatar" style="background-color: {user.color}" title={user.username}>
								{user.username.charAt(0).toUpperCase()}
							</div>
						{/if}
					{/each}
				</div>
				<!-- 評論按鈕 -->
				<button
					type="button"
					class="toolbar-button"
					onclick={() => (showCommentPanel = true)}
					title="評論"
					aria-label="評論"
				>
					<MessageSquare size={20} />
				</button>
				<!-- AI 按鈕 -->
				<button
					type="button"
					class="toolbar-button ai"
					onclick={openAIDialog}
					title="AI Writing Assistant"
					aria-label="AI Writing Assistant"
					disabled={!canWrite}
				>
					<Sparkles size={20} />
				</button>
				<!-- 版本歷史按鈕 -->
				<button
					type="button"
					class="toolbar-button"
					onclick={() => (showVersionHistory = true)}
					title="版本歷史"
					aria-label="版本歷史"
				>
					<Clock size={20} />
				</button>
				{#if isOwner}
					<button onclick={() => (showShareModal = true)} class="share-button" title="Share">
						<Share2 size={18} />
						<span class="hidden sm:inline">Share</span>
					</button>
				{/if}
				{#if isOwner}
					<button onclick={handleDelete} class="delete-button" title="Delete">
						<Trash2 size={18} />
						<span class="hidden sm:inline">Delete</span>
					</button>
				{/if}
			</div>
		{/if}
	</header>

	<main class="main-content">
		{#if isLoading}
			<div class="load-state" data-testid="loading-state">
				<div class="loading-spinner"></div>
				<p class="load-state-text">Loading document...</p>
			</div>
		{:else if loadError}
			<div class="load-state" data-testid="error-state">
				<div class="load-state-icon">
					<TriangleAlert size={48} />
				</div>
				<h2 class="load-state-title">Failed to load document</h2>
				<p class="load-state-text">{loadError}</p>
				<div class="load-state-actions">
					<button onclick={loadDocument} class="retry-button">
						<RefreshCw size={16} />
						<span>Retry</span>
					</button>
					<a href="/dashboard" class="back-link">Back to Dashboard</a>
				</div>
			</div>
		{:else}
			<div class="editor-wrapper">
				<!-- Svelte 5: Use onTextChange callback prop instead of on:text-change event -->
				<QuillEditor
					bind:this={quillEditor}
					bind:value={content}
					bind:editor
					onTextChange={handleContentChange}
					onSelectionChange={handleSelectionChange}
					disabled={!canWrite}
				/>
			</div>
		{/if}
	</main>
</div>

<!-- Share Modal -->
{#if showShareModal}
	<div class="modal-overlay">
		<div class="modal-content">
			<div class="modal-header">
				<h2 class="modal-title">Share "{title}"</h2>
				<button
					type="button"
					class="modal-close"
					onclick={() => (showShareModal = false)}
					aria-label="Close"
				>
					<X size={20} />
				</button>
			</div>

			{#if isOwner}
				<div class="collaborator-form">
					<input
						type="text"
						bind:value={newCollaboratorUsername}
						placeholder="Enter username"
						class="collaborator-input"
					/>
					<select bind:value={newCollaboratorPermission} class="permission-select">
						<option value="write">Can Edit</option>
						<option value="read">View Only</option>
					</select>
					<button onclick={handleAddCollaborator} class="add-button">
						<Plus size={18} />
						<span>Add</span>
					</button>
				</div>
			{/if}

			<h3 class="collaborators-heading">Collaborators</h3>
			<ul class="collaborators-list">
				{#each collaborators as collaborator (collaborator.id)}
					<li class="collaborator-item">
						<div class="collaborator-info">
							<span class="collaborator-name">{collaborator.username}</span>
							<span class="collaborator-email">{collaborator.email}</span>
							<span class="permission-badge {collaborator.permission}">
								{collaborator.permission === 'write' ? 'Can Edit' : 'View Only'}
							</span>
						</div>
						{#if isOwner}
							<button
								onclick={() => openRemoveConfirm(collaborator)}
								class="remove-button"
								title="Remove collaborator"
							>
								<UserMinus size={16} />
							</button>
						{/if}
					</li>
				{/each}
			</ul>

			<div class="modal-actions">
				<button onclick={() => (showShareModal = false)} class="done-button"> Done </button>
			</div>
		</div>
	</div>
{/if}

<!-- Remove Collaborator Confirmation Modal -->
{#if showRemoveConfirmModal && collaboratorToRemove}
	<div class="modal-overlay">
		<div class="modal-content">
			<div class="modal-header">
				<h2 class="modal-title">Remove Collaborator</h2>
				<button
					type="button"
					class="modal-close"
					onclick={() => {
						showRemoveConfirmModal = false;
						collaboratorToRemove = null;
					}}
					aria-label="Close"
				>
					<X size={20} />
				</button>
			</div>
			<p class="confirm-text">
				Are you sure you want to remove
				<strong class="font-semibold">{collaboratorToRemove.username}</strong>
				from this document?
			</p>
			<div class="modal-actions">
				<button
					onclick={() => {
						showRemoveConfirmModal = false;
						collaboratorToRemove = null;
					}}
					class="cancel-button"
				>
					Cancel
				</button>
				<button onclick={confirmRemoveCollaborator} class="confirm-remove-button">
					<UserMinus size={16} />
					<span>Remove</span>
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- 版本歷史面板 -->
<VersionHistoryPanel
	{documentId}
	bind:isOpen={showVersionHistory}
	onRestore={handleVersionRestore}
/>

<!-- AI 對話框 -->
<AIDialog bind:isOpen={showAIDialog} selectedText={selectedTextForAI} onApply={applyAIResult} />

<ConfirmDialog
	bind:isOpen={showDeleteConfirm}
	title="刪除文件"
	message="確定要刪除這份文件嗎？此操作無法復原。"
	confirmText="刪除"
	variant="danger"
	onConfirm={confirmDelete}
/>

<!-- 評論面板 -->
<CommentPanel
	bind:this={commentPanel}
	{documentId}
	bind:isOpen={showCommentPanel}
	{canWrite}
	{currentUserId}
	{isOwner}
/>

<style>
	.page-container {
		display: flex;
		flex-direction: column;
		height: 100vh;
		background-color: var(--color-primary-50);
		max-width: 100vw;
		overflow-x: hidden;
	}

	.header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		background-color: white;
		border-bottom: 1px solid var(--color-primary-200);
		padding: 0.5rem 0.75rem;
		position: sticky;
		top: 0;
		z-index: 10;
		gap: 0.5rem;
	}

	@media (min-width: 640px) {
		.header {
			padding: 0.75rem 1.5rem;
			gap: 1rem;
		}
	}

	.header-left {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		min-width: 0;
		flex: 1;
	}

	@media (min-width: 640px) {
		.header-left {
			gap: 0.75rem;
		}
	}

	.logo-link {
		color: var(--color-primary-500);
		transition: color 0.15s ease;
	}
	.logo-link:hover {
		color: var(--color-primary-700);
	}

	.doc-info {
		display: flex;
		flex-direction: column;
		min-width: 0;
		flex: 1;
	}

	.doc-title-input {
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--color-primary-900);
		background-color: transparent;
		border: 1px solid transparent;
		border-radius: 0.5rem;
		padding: 0.125rem 0.25rem;
		outline: none;
		transition: all 0.15s ease;
		min-width: 0;
		width: 100%;
	}

	@media (min-width: 640px) {
		.doc-title-input {
			font-size: 1.125rem;
			padding: 0.25rem 0.5rem;
		}
	}

	.doc-title-input:focus {
		background-color: var(--color-primary-50);
		border-color: var(--color-primary-300);
		box-shadow: 0 0 0 3px rgba(13, 148, 136, 0.1);
	}

	.doc-status {
		font-size: 0.625rem;
		color: var(--color-primary-500);
		padding-left: 0.25rem;
		height: 1rem;
		display: flex;
		align-items: center;
	}

	@media (min-width: 640px) {
		.doc-status {
			font-size: 0.75rem;
			padding-left: 0.5rem;
			height: 1.25rem;
		}
	}

	.header-right {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		flex-shrink: 0;
	}

	@media (min-width: 640px) {
		.header-right {
			gap: 0.5rem;
		}
	}

	/* Toolbar button base style */
	.toolbar-button {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 0.375rem;
		background-color: transparent;
		border: 1px solid var(--color-primary-200);
		border-radius: 0.5rem;
		color: var(--color-primary-600);
		cursor: pointer;
		transition: all 0.15s ease;
		flex-shrink: 0;
	}

	@media (min-width: 640px) {
		.toolbar-button {
			padding: 0.5rem;
		}
	}

	.toolbar-button:hover:not(:disabled) {
		background-color: var(--color-primary-50);
		color: var(--color-primary-700);
		border-color: var(--color-primary-300);
	}

	.toolbar-button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	/* AI button special styling */
	.toolbar-button.ai {
		border-color: var(--color-cta-200);
		color: var(--color-cta-500);
	}

	.toolbar-button.ai:hover:not(:disabled) {
		background-color: var(--color-cta-50);
		color: var(--color-cta-600);
		border-color: var(--color-cta-300);
	}

	.share-button {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.25rem;
		padding: 0.375rem;
		background-color: var(--color-primary-600);
		color: white;
		font-weight: 500;
		border-radius: 0.5rem;
		border: none;
		cursor: pointer;
		transition: all 0.15s ease;
		flex-shrink: 0;
	}

	@media (min-width: 640px) {
		.share-button {
			gap: 0.5rem;
			padding: 0.5rem 1rem;
		}
	}

	.share-button:hover {
		background-color: var(--color-primary-700);
	}

	.delete-button {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.25rem;
		padding: 0.375rem;
		background-color: rgba(239, 68, 68, 0.1);
		color: var(--color-danger);
		font-weight: 500;
		border-radius: 0.5rem;
		border: none;
		cursor: pointer;
		transition: all 0.15s ease;
		flex-shrink: 0;
	}

	@media (min-width: 640px) {
		.delete-button {
			gap: 0.5rem;
			padding: 0.5rem 1rem;
		}
	}

	.delete-button:hover {
		background-color: rgba(239, 68, 68, 0.2);
	}

	.main-content {
		flex-grow: 1;
		overflow-y: auto;
		padding-top: 1rem;
		padding-bottom: 2rem;
	}

	@media (min-width: 640px) {
		.main-content {
			padding-top: 2rem;
			padding-bottom: 4rem;
		}
	}

	.editor-wrapper {
		max-width: 56rem;
		min-height: 100%;
		margin: 0 auto;
		background-color: white;
		box-shadow:
			0 4px 6px -1px rgba(0, 0, 0, 0.1),
			0 2px 4px -1px rgba(0, 0, 0, 0.06);
		border-radius: 0;
		padding: 1rem;
		border: none;
		border-top: 1px solid var(--color-primary-200);
		border-bottom: 1px solid var(--color-primary-200);
	}

	@media (min-width: 640px) {
		.editor-wrapper {
			border-radius: 0.75rem;
			padding: 2rem;
			border: 1px solid var(--color-primary-200);
			margin: 0 1rem;
		}
	}

	@media (min-width: 1024px) {
		.editor-wrapper {
			padding: 4rem;
			margin: 0 auto;
		}
	}

	/* Modal Styles */
	.modal-overlay {
		position: fixed;
		inset: 0;
		background-color: rgba(0, 0, 0, 0.5);
		backdrop-filter: blur(2px);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 50;
	}
	.modal-content {
		background-color: white;
		border-radius: 1rem;
		box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
		padding: 1.5rem;
		width: 100%;
		max-width: 28rem;
		margin: 1rem;
	}
	.modal-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 1.5rem;
	}
	.modal-title {
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--color-primary-900);
	}
	.modal-close {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 0.25rem;
		background: none;
		border: none;
		color: var(--color-primary-400);
		cursor: pointer;
		border-radius: 0.375rem;
		transition: all 0.15s ease;
	}
	.modal-close:hover {
		color: var(--color-primary-600);
		background-color: var(--color-primary-100);
	}
	.collaborator-form {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		margin-bottom: 1.5rem;
	}
	@media (min-width: 480px) {
		.collaborator-form {
			flex-direction: row;
		}
	}
	.collaborator-input {
		flex-grow: 1;
		width: 100%;
		border: 1px solid var(--color-primary-300);
		border-radius: 0.5rem;
		padding: 0.5rem 0.75rem;
		transition: all 0.15s ease;
	}
	@media (min-width: 480px) {
		.collaborator-input {
			width: 0;
		}
	}
	.collaborator-input:focus {
		outline: none;
		border-color: var(--color-primary-500);
		box-shadow: 0 0 0 3px rgba(13, 148, 136, 0.1);
	}
	.add-button {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.25rem;
		padding: 0.5rem 1rem;
		width: 100%;
		background-color: var(--color-primary-600);
		color: white;
		font-weight: 500;
		border-radius: 0.5rem;
		border: none;
		cursor: pointer;
		transition: all 0.15s ease;
	}
	@media (min-width: 480px) {
		.add-button {
			width: auto;
		}
	}
	.add-button:hover {
		background-color: var(--color-primary-700);
	}
	.collaborators-heading {
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--color-primary-700);
		margin-bottom: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}
	.collaborators-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		max-height: 15rem;
		overflow-y: auto;
	}
	.collaborator-item {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.75rem;
		background-color: var(--color-primary-50);
		border-radius: 0.5rem;
		transition: background-color 0.15s ease;
	}
	.collaborator-item:hover {
		background-color: var(--color-primary-100);
	}
	.collaborator-info {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.5rem;
	}
	.collaborator-name {
		font-weight: 500;
		color: var(--color-primary-800);
	}
	.collaborator-email {
		font-size: 0.875rem;
		color: var(--color-primary-500);
	}
	.remove-button {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 0.375rem;
		color: var(--color-primary-400);
		background: none;
		border: none;
		border-radius: 0.375rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}
	.remove-button:hover {
		color: var(--color-danger);
		background-color: rgba(239, 68, 68, 0.1);
	}
	.modal-actions {
		margin-top: 1.5rem;
		display: flex;
		justify-content: flex-end;
		gap: 0.5rem;
	}
	.done-button {
		padding: 0.5rem 1.25rem;
		background-color: var(--color-primary-100);
		color: var(--color-primary-700);
		font-weight: 500;
		border-radius: 0.5rem;
		border: none;
		cursor: pointer;
		transition: all 0.15s ease;
	}
	.done-button:hover {
		background-color: var(--color-primary-200);
	}

	/* Confirmation Modal Specific Styles */
	.confirm-text {
		margin-bottom: 1.5rem;
		color: var(--color-primary-700);
		line-height: 1.5;
	}

	.cancel-button {
		padding: 0.5rem 1rem;
		background-color: var(--color-primary-100);
		color: var(--color-primary-700);
		font-weight: 500;
		border-radius: 0.5rem;
		border: none;
		cursor: pointer;
		transition: all 0.15s ease;
	}
	.cancel-button:hover {
		background-color: var(--color-primary-200);
	}

	.confirm-remove-button {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.5rem 1rem;
		background-color: var(--color-danger);
		color: white;
		font-weight: 500;
		border-radius: 0.5rem;
		border: none;
		cursor: pointer;
		transition: all 0.15s ease;
	}
	.confirm-remove-button:hover {
		background-color: #dc2626;
	}

	/* Title row with read-only badge */
	.title-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	/* Read-only badge */
	.read-only-badge {
		background-color: var(--color-cta-100);
		color: var(--color-cta-700);
		padding: 2px 8px;
		border-radius: 9999px;
		font-size: 11px;
		font-weight: 500;
		white-space: nowrap;
	}

	/* Disabled title input */
	.doc-title-input:disabled {
		cursor: not-allowed;
		opacity: 0.7;
	}

	/* Permission select dropdown */
	.permission-select {
		padding: 0.5rem;
		padding-right: 1.5rem;
		border: 1px solid var(--color-primary-300);
		border-radius: 0.5rem;
		background-color: white;
		color: var(--color-primary-700);
		cursor: pointer;
		min-width: 115px;
		width: 100%;
		transition: all 0.15s ease;
	}
	@media (min-width: 480px) {
		.permission-select {
			width: auto;
		}
	}
	.permission-select:focus {
		outline: none;
		border-color: var(--color-primary-500);
		box-shadow: 0 0 0 3px rgba(13, 148, 136, 0.1);
	}

	/* Permission badges in collaborator list */
	.permission-badge {
		padding: 2px 8px;
		border-radius: 9999px;
		font-size: 11px;
		font-weight: 500;
	}

	.permission-badge.write {
		background-color: #d1fae5;
		color: #065f46;
	}

	.permission-badge.read {
		background-color: var(--color-primary-100);
		color: var(--color-primary-700);
	}

	/* Online users avatars */
	.online-users {
		display: none;
		align-items: center;
		gap: -0.25rem;
		margin-right: 0.5rem;
	}

	@media (min-width: 480px) {
		.online-users {
			display: flex;
		}
	}

	@media (min-width: 640px) {
		.online-users {
			margin-right: 1rem;
		}
	}

	.user-avatar {
		width: 1.5rem;
		height: 1.5rem;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		color: white;
		font-size: 0.625rem;
		font-weight: 600;
		border: 2px solid white;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
		cursor: default;
		margin-left: -0.25rem;
		transition: transform 0.15s ease;
	}

	@media (min-width: 640px) {
		.user-avatar {
			width: 2rem;
			height: 2rem;
			font-size: 0.75rem;
		}
	}

	.user-avatar:first-child {
		margin-left: 0;
	}

	.user-avatar:hover {
		transform: scale(1.1);
		z-index: 1;
	}

	/* Document loading & error states */
	.load-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 1rem;
		padding: 4rem 2rem;
		text-align: center;
	}

	.loading-spinner {
		width: 2.5rem;
		height: 2.5rem;
		border: 3px solid var(--color-primary-200);
		border-top-color: var(--color-primary-600);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	.load-state-icon {
		color: var(--color-danger);
	}

	.load-state-title {
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--color-primary-900);
		margin: 0;
	}

	.load-state-text {
		font-size: 0.875rem;
		color: var(--color-primary-500);
		margin: 0;
		max-width: 24rem;
	}

	.load-state-actions {
		display: flex;
		align-items: center;
		gap: 1rem;
		margin-top: 0.5rem;
	}

	.retry-button {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.5rem 1.25rem;
		background-color: var(--color-primary-600);
		color: white;
		font-weight: 500;
		border-radius: 0.5rem;
		border: none;
		cursor: pointer;
		transition: background-color 0.15s ease;
	}

	.retry-button:hover {
		background-color: var(--color-primary-700);
	}

	.back-link {
		padding: 0.5rem 1.25rem;
		color: var(--color-primary-600);
		font-weight: 500;
		border-radius: 0.5rem;
		text-decoration: none;
		transition: background-color 0.15s ease;
	}

	.back-link:hover {
		background-color: var(--color-primary-100);
	}
</style>
