<script lang="ts">
	import { page } from '$app/stores';
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import QuillEditor from '$lib/components/QuillEditor.svelte';
	import VersionHistoryPanel from '$lib/components/VersionHistoryPanel.svelte';
	import { get, put, del, post, logout, type Collaborator } from '$lib/auth';
	import { toast } from '@zerodevx/svelte-toast';
	import type { QuillDelta, QuillType } from '$lib/types/quill';
	import type { PresenceUser } from '$lib/types/cursor';
	import Delta from 'quill-delta';

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

	// Toast 主題
	const errorTheme = {
		'--toastBackground': '#F56565',
		'--toastColor': 'white',
		'--toastBarBackground': '#C53030'
	};

	const warningTheme = {
		'--toastBackground': '#ED8936',
		'--toastColor': 'white',
		'--toastBarBackground': '#C05621'
	};

	// Svelte 5: $page store auto-subscription still works
	const documentId = $page.params.document_id;

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

	// Throttle state for WebSocket delta sending
	let pendingDelta: QuillDelta | null = $state(null);
	let throttleTimeout: ReturnType<typeof setTimeout> | undefined = $state(undefined);
	let lastSendTime = $state(0);
	const THROTTLE_INTERVAL = 150; // ms（100-200ms 範圍）

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

	// Cursor and Presence state
	let quillEditor: QuillEditor;
	let onlineUsers = $state<Map<string, PresenceUser>>(new Map());
	let currentUserId = $state<string | null>(null);

	// Cursor change throttle state
	let cursorThrottleTimer: ReturnType<typeof setTimeout> | null = $state(null);
	let pendingCursor: { index: number; length: number } | null = $state(null);
	const CURSOR_THROTTLE_INTERVAL = 150; // ms

	async function getCollaborators() {
		try {
			collaborators = await get(`/documents/${documentId}/collaborators/`);
		} catch (error) {
			console.error('Failed to fetch collaborators:', error);
			toast.push('Could not load collaborators.', {
				theme: {
					'--toastBackground': '#F56565',
					'--toastColor': 'white',
					'--toastBarBackground': '#C53030'
				}
			});
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
			toast.push(`Successfully added ${newCollaborator.username} as a collaborator.`, {
				theme: {
					'--toastBackground': '#48BB78',
					'--toastColor': 'white',
					'--toastBarBackground': '#2F855A'
				}
			});
		} catch (error: unknown) {
			console.error('Failed to add collaborator:', error);
			const message = error instanceof Error ? error.message : 'Failed to add collaborator.';
			toast.push(message, {
				theme: {
					'--toastBackground': '#F56565',
					'--toastColor': 'white',
					'--toastBarBackground': '#C53030'
				}
			});
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
			toast.push('Collaborator removed.', {
				theme: {
					'--toastBackground': '#48BB78',
					'--toastColor': 'white',
					'--toastBarBackground': '#2F855A'
				}
			});
			collaborators = collaborators.filter((c) => c.id !== collaboratorToRemove!.id);
		} catch (error) {
			console.error('Failed to remove collaborator:', error);
			toast.push('Failed to remove collaborator.', {
				theme: {
					'--toastBackground': '#F56565',
					'--toastColor': 'white',
					'--toastBarBackground': '#C53030'
				}
			});
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
	function handleWsError(code: number, message?: string) {
		switch (code) {
			case WS_CLOSE_CODES.TOKEN_EXPIRED:
			case WS_CLOSE_CODES.AUTH_FAILED:
				toast.push('Session expired. Please login again.', { theme: errorTheme });
				logout();
				goto('/login');
				break;
			case WS_CLOSE_CODES.PERMISSION_DENIED:
				toast.push(message || 'You do not have permission to access this document.', {
					theme: errorTheme
				});
				goto('/dashboard');
				break;
			case WS_CLOSE_CODES.DOCUMENT_NOT_FOUND:
				toast.push('Document not found.', { theme: errorTheme });
				goto('/dashboard');
				break;
			case WS_CLOSE_CODES.TOO_MANY_CONNECTIONS:
				toast.push('Too many open tabs. Please close some and refresh.', { theme: errorTheme });
				break;
			case WS_CLOSE_CODES.RATE_LIMITED:
				toast.push('Sending too fast. Please slow down.', { theme: warningTheme });
				break;
			default:
				toast.push(message || 'Connection lost. Please refresh the page.', { theme: errorTheme });
		}
	}

	onMount(async () => {
		try {
			const doc = await get(`/documents/${documentId}/`);
			title = doc.title;
			isOwner = doc.is_owner === true; // Strict check
			canWrite = doc.can_write !== false; // Get initial permission from API
			lastSavedTime = doc.updated_at;
			if (content.ops.length === 0) {
				content = doc.content || { ops: [] };
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
							toast.push(`Too fast! Wait ${Math.ceil(data.retry_after)}s`, {
								theme: warningTheme
							});
						} else if (data.error_code === 'READ_ONLY') {
							toast.push('You have read-only access to this document.', {
								theme: warningTheme
							});
						} else {
							toast.push(data.message || 'An error occurred.', { theme: errorTheme });
						}
						break;
				}
			};

			socket.onclose = (event) => {
				console.log('WebSocket closed:', event.code, event.reason);
				saveStatus = 'error';

				// 根據 close code 處理
				if (event.code >= 4001 && event.code <= 4008) {
					handleWsError(event.code, event.reason);
				} else if (event.code !== 1000 && event.code !== 1001) {
					// 非正常關閉（1000=正常, 1001=離開頁面）
					toast.push('Connection lost. Please refresh the page.', { theme: errorTheme });
				}
			};

			socket.onerror = (error) => {
				console.error('WebSocket error:', error);
				saveStatus = 'error';
			};
		} catch (error) {
			console.error('Failed to fetch document:', error);
			saveStatus = 'error';
		}
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
				toast.push('Failed to save document.', {
					theme: {
						'--toastBackground': '#F56565',
						'--toastColor': 'white',
						'--toastBarBackground': '#C53030'
					}
				});
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

	async function handleDelete() {
		if (!confirm('Are you sure you want to delete this document? This action cannot be undone.')) {
			return;
		}
		try {
			await del(`/documents/${documentId}/`);
			toast.push('Document deleted successfully.', {
				theme: {
					'--toastBackground': '#48BB78',
					'--toastColor': 'white',
					'--toastBarBackground': '#2F855A'
				}
			});
			await goto('/dashboard');
		} catch (error) {
			console.error('Failed to delete document:', error);
			toast.push('Failed to delete document.', {
				theme: {
					'--toastBackground': '#F56565',
					'--toastColor': 'white',
					'--toastBarBackground': '#C53030'
				}
			});
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

	// 還原版本後重新載入文件
	async function handleVersionRestore() {
		try {
			const doc = await get(`/documents/${documentId}/`);
			title = doc.title;
			content = doc.content || { ops: [] };
			// 更新編輯器內容
			if (editor) {
				editor.setContents(content, 'silent');
			}
			lastSavedTime = doc.updated_at;
			saveStatus = 'saved';
			setTimeout(() => {
				if (saveStatus === 'saved') saveStatus = 'idle';
			}, 2000);
		} catch (error) {
			console.error('Failed to reload document after restore:', error);
			toast.push('Failed to reload document.', {
				theme: errorTheme
			});
		}
	}

	onDestroy(() => {
		// Send any pending delta before closing
		if (pendingDelta && socket?.readyState === WebSocket.OPEN) {
			socket.send(JSON.stringify({ delta: pendingDelta }));
		}

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
				<svg
					class="logo-icon"
					fill="currentColor"
					viewBox="0 0 24 24"
					xmlns="http://www.w3.org/2000/svg"
					><path
						d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zM6 20V4h7v5h5v11H6z"
					/></svg
				>
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
		<div class="header-right">
			<!-- 在線用戶頭像 -->
			<div class="online-users">
				{#each [...onlineUsers.entries()] as [userId, user]}
					{#if userId !== currentUserId}
						<div
							class="user-avatar"
							style="background-color: {user.color}"
							title={user.username}
						>
							{user.username.charAt(0).toUpperCase()}
						</div>
					{/if}
				{/each}
			</div>
			<!-- 版本歷史按鈕 -->
			<button
				type="button"
				class="history-button"
				onclick={() => (showVersionHistory = true)}
				title="版本歷史"
				aria-label="版本歷史"
			>
				<svg class="history-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
					/>
				</svg>
			</button>
			{#if isOwner}
				<button onclick={() => (showShareModal = true)} class="share-button">
					<svg
						class="share-icon"
						fill="currentColor"
						viewBox="0 0 20 20"
						xmlns="http://www.w3.org/2000/svg"
						><path
							d="M15 8a3 3 0 10-2.977-2.63l-4.94 2.47a3 3 0 100 4.319l4.94 2.47a3 3 0 10.895-1.789l-4.94-2.47a3.027 3.027 0 000-.74l4.94-2.47C13.456 7.68 14.19 8 15 8z"
						/></svg
					>
					<span>Share</span>
				</button>
			{/if}
			{#if isOwner}
				<button onclick={handleDelete} class="delete-button"> Delete </button>
			{/if}
		</div>
	</header>

	<main class="main-content">
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
	</main>
</div>

<!-- Share Modal -->
{#if showShareModal}
	<div class="modal-overlay">
		<div class="modal-content">
			<h2 class="modal-title">Share "{title}"</h2>

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
					<button onclick={handleAddCollaborator} class="add-button">Add</button>
				</div>
			{/if}

			<h3 class="collaborators-heading">Collaborators</h3>
			<ul class="collaborators-list">
				{#each collaborators as collaborator (collaborator.id)}
					<li class="collaborator-item">
						<div class="collaborator-info">
							<span>{collaborator.username}</span>
							<span class="collaborator-email">({collaborator.email})</span>
							<span class="permission-badge {collaborator.permission}">
								{collaborator.permission === 'write' ? 'Can Edit' : 'View Only'}
							</span>
						</div>
						{#if isOwner}
							<button onclick={() => openRemoveConfirm(collaborator)} class="remove-button"
								>Remove</button
							>
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
			<h2 class="modal-title">Remove Collaborator</h2>
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
				<button onclick={confirmRemoveCollaborator} class="confirm-remove-button"> Remove </button>
			</div>
		</div>
	</div>
{/if}

<!-- 版本歷史面板 -->
<VersionHistoryPanel
	documentId={documentId}
	bind:isOpen={showVersionHistory}
	onRestore={handleVersionRestore}
/>

<style>
	.page-container {
		display: flex;
		flex-direction: column;
		height: 100vh;
		background-color: #f7fafc; /* gray-100 */
	}

	.header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		background-color: white;
		border-bottom: 1px solid #e2e8f0; /* gray-200 */
		padding: 0.5rem 1rem;
		position: sticky;
		top: 0;
		z-index: 10;
	}

	.header-left {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.logo-link {
		color: #4299e1; /* blue-500 */
	}
	.logo-link:hover {
		color: #2b6cb0; /* blue-700 */
	}
	.logo-icon {
		width: 2.5rem;
		height: 2.5rem;
	}

	.doc-info {
		display: flex;
		flex-direction: column;
	}

	.doc-title-input {
		font-size: 1.125rem; /* text-lg */
		background-color: transparent;
		border-radius: 0.375rem; /* rounded-md */
		padding: 0.25rem 0.5rem;
		outline: none;
	}
	.doc-title-input:focus {
		background-color: #f7fafc; /* gray-100 */
		box-shadow: 0 0 0 2px #63b3ed; /* ring-2 ring-blue-400 */
	}

	.doc-status {
		font-size: 0.75rem; /* text-xs */
		color: #718096; /* gray-500 */
		padding-left: 0.5rem;
		height: 1.25rem; /* h-5 */
		display: flex;
		align-items: center;
	}

	.header-right {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.share-button {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 1rem;
		background-color: #4299e1; /* blue-600 */
		color: white;
		font-weight: 600;
		border-radius: 0.375rem; /* rounded-md */
		border: none;
		cursor: pointer;
	}
	.share-button:hover {
		background-color: #3182ce; /* blue-700 */
	}
	.share-icon {
		width: 1.25rem;
		height: 1.25rem;
	}

	.delete-button {
		padding: 0.5rem 0.75rem;
		background-color: #fed7d7; /* red-100 */
		color: #c53030; /* red-700 */
		font-weight: 600;
		border-radius: 0.375rem; /* rounded-md */
		border: none;
		cursor: pointer;
	}
	.delete-button:hover {
		background-color: #fbb6b6; /* red-200 */
	}

	.main-content {
		flex-grow: 1;
		overflow-y: auto;
		padding-top: 2rem;
		padding-bottom: 4rem;
	}

	.editor-wrapper {
		max-width: 80rem; /* max-w-4xl */
		min-height: 100%;
		margin: 0 auto;
		background-color: white;
		box-shadow:
			0 20px 25px -5px rgba(0, 0, 0, 0.1),
			0 10px 10px -5px rgba(0, 0, 0, 0.04); /* shadow-2xl */
		border-radius: 0.5rem; /* rounded-lg */
		padding: 4rem;
		border: 1px solid #e2e8f0; /* border */
	}

	/* Modal Styles */
	.modal-overlay {
		position: fixed;
		inset: 0;
		background-color: rgba(0, 0, 0, 0.5);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 50;
	}
	.modal-content {
		background-color: white;
		border-radius: 0.5rem; /* rounded-lg */
		box-shadow:
			0 20px 25px -5px rgba(0, 0, 0, 0.1),
			0 10px 10px -5px rgba(0, 0, 0, 0.04); /* shadow-xl */
		padding: 1.5rem;
		width: 100%;
		max-width: 32rem; /* max-w-md */
	}
	.modal-title {
		font-size: 1.5rem; /* text-2xl */
		font-weight: 700;
		margin-bottom: 1rem;
	}
	.collaborator-form {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 1rem;
	}
	.collaborator-input {
		flex-grow: 1;
		border: 1px solid #d2d6dc; /* border-gray-300 */
		border-radius: 0.375rem; /* rounded-md */
		padding: 0.5rem 0.75rem;
	}
	.collaborator-input:focus {
		box-shadow: 0 0 0 2px #63b3ed; /* ring-blue-500 */
		border-color: #4299e1; /* border-blue-500 */
	}
	.add-button {
		padding: 0.5rem 1rem;
		background-color: #4299e1; /* blue-600 */
		color: white;
		font-weight: 600;
		border-radius: 0.375rem; /* rounded-md */
		border: none;
		cursor: pointer;
	}
	.add-button:hover {
		background-color: #3182ce; /* blue-700 */
	}
	.collaborators-heading {
		font-size: 1.125rem; /* text-lg */
		font-weight: 600;
		margin-bottom: 0.5rem;
	}
	.collaborators-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		max-height: 15rem; /* max-h-60 */
		overflow-y: auto;
	}
	.collaborator-item {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.5rem;
		background-color: #f7fafc; /* gray-100 */
		border-radius: 0.375rem; /* rounded-md */
	}
	.collaborator-email {
		font-size: 0.875rem; /* text-sm */
		color: #a0aec0; /* gray-500 */
		margin-left: 0.5rem;
	}
	.remove-button {
		color: #e53e3e; /* red-500 */
		background: none;
		border: none;
		cursor: pointer;
	}
	.remove-button:hover {
		color: #c53030; /* red-700 */
	}
	.modal-actions {
		margin-top: 1.5rem;
		text-align: right;
	}
	.done-button {
		padding: 0.5rem 1rem;
		background-color: #e2e8f0; /* gray-300 */
		color: #2d3748; /* gray-800 */
		font-weight: 600;
		border-radius: 0.375rem; /* rounded-md */
		border: none;
		cursor: pointer;
	}
	.done-button:hover {
		background-color: #cbd5e0; /* gray-400 */
	}

	/* Confirmation Modal Specific Styles */
	.confirm-text {
		margin-bottom: 1.5rem;
		color: #4a5568; /* gray-700 */
	}

	.cancel-button {
		padding: 0.5rem 1rem;
		background-color: #e2e8f0; /* gray-300 */
		color: #2d3748; /* gray-800 */
		font-weight: 600;
		border-radius: 0.375rem; /* rounded-md */
		border: none;
		cursor: pointer;
		margin-right: 0.5rem;
	}
	.cancel-button:hover {
		background-color: #cbd5e0; /* gray-400 */
	}

	.confirm-remove-button {
		padding: 0.5rem 1rem;
		background-color: #e53e3e; /* red-600 */
		color: white;
		font-weight: 600;
		border-radius: 0.375rem; /* rounded-md */
		border: none;
		cursor: pointer;
	}
	.confirm-remove-button:hover {
		background-color: #c53030; /* red-700 */
	}

	/* Title row with read-only badge */
	.title-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	/* Read-only badge */
	.read-only-badge {
		background-color: #fef3c7; /* amber-100 */
		color: #92400e; /* amber-800 */
		padding: 2px 8px;
		border-radius: 4px;
		font-size: 12px;
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
		border: 1px solid #d2d6dc;
		border-radius: 0.375rem;
		background-color: white;
		cursor: pointer;
		min-width: 115px;
	}
	.permission-select:focus {
		box-shadow: 0 0 0 2px #63b3ed;
		border-color: #4299e1;
	}

	/* Collaborator info container */
	.collaborator-info {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.25rem;
	}

	/* Permission badges in collaborator list */
	.permission-badge {
		padding: 2px 6px;
		border-radius: 4px;
		font-size: 11px;
		font-weight: 500;
		margin-left: 0.5rem;
	}

	.permission-badge.write {
		background-color: #d1fae5; /* green-100 */
		color: #065f46; /* green-800 */
	}

	.permission-badge.read {
		background-color: #e0e7ff; /* indigo-100 */
		color: #3730a3; /* indigo-800 */
	}

	/* Online users avatars */
	.online-users {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		margin-right: 1rem;
	}

	.user-avatar {
		width: 2rem;
		height: 2rem;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		color: white;
		font-size: 0.875rem;
		font-weight: 600;
		border: 2px solid white;
		box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
		cursor: default;
	}

	.user-avatar:hover {
		transform: scale(1.1);
		transition: transform 0.15s ease;
	}

	/* History button */
	.history-button {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 0.5rem;
		background-color: transparent;
		border: 1px solid #e2e8f0;
		border-radius: 0.375rem;
		color: #4a5568;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.history-button:hover {
		background-color: #f7fafc;
		color: #2d3748;
		border-color: #cbd5e0;
	}

	.history-icon {
		width: 1.25rem;
		height: 1.25rem;
	}
</style>
