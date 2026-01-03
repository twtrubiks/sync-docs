<script lang="ts">
	import { page } from '$app/stores';
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import QuillEditor from '$lib/components/QuillEditor.svelte';
	import { get, put, del, post } from '$lib/auth';
	import { toast } from '@zerodevx/svelte-toast';

	// Svelte 5: $page store auto-subscription still works
	const documentId = $page.params.document_id;

	// Svelte 5 Runes: use $state() for reactive state
	let title = $state('');
	let content: any = $state({}); // Quill's content can be an object (Delta)
	let editor: any = $state(null); // To hold the Quill instance
	let socket: WebSocket | null = $state(null);
	let owner: { username: string } | null = $state(null);
	let isOwner = $state(false);
	let lastSavedTime: string | null = $state(null);
	let saveStatus: 'idle' | 'unsaved' | 'saving' | 'saved' | 'error' | 'connecting' = $state('connecting');
	let debounceTimeout: any = $state(null);

	// State for sharing modal
	let showShareModal = $state(false);
	let collaborators: any[] = $state([]);
	let newCollaboratorUsername = $state('');

	// State for remove confirmation modal
	let showRemoveConfirmModal = $state(false);
	let collaboratorToRemove: { id: number; username: string } | null = $state(null);

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
				username: newCollaboratorUsername
			});
			collaborators = [...collaborators, newCollaborator];
			newCollaboratorUsername = ''; // Clear input
			toast.push(`Successfully added ${newCollaborator.username} as a collaborator.`, {
				theme: {
					'--toastBackground': '#48BB78',
					'--toastColor': 'white',
					'--toastBarBackground': '#2F855A'
				}
			});
		} catch (error: any) {
			console.error('Failed to add collaborator:', error);
			toast.push(error.message || 'Failed to add collaborator.', {
				theme: {
					'--toastBackground': '#F56565',
					'--toastColor': 'white',
					'--toastBarBackground': '#C53030'
				}
			});
		}
	}

	function openRemoveConfirm(collaborator: { id: number; username: string }) {
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

	onMount(async () => {
		try {
			const doc = await get(`/documents/${documentId}/`);
			title = doc.title;
			owner = doc.owner;
			isOwner = doc.is_owner === true; // Strict check
			lastSavedTime = doc.updated_at;
			if (Object.keys(content).length === 0) {
				content = doc.content || {};
			}

			const token = localStorage.getItem('access_token');
			if (!token) {
				console.error('No auth token found, WebSocket connection aborted.');
				saveStatus = 'error';
				return;
			}
			const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
			const wsUrl = `${wsProtocol}//localhost:8000/ws/docs/${documentId}/?token=${token}`;
			socket = new WebSocket(wsUrl);

			socket.onopen = () => {
				console.log('WebSocket connection established');
				saveStatus = 'idle';
			};

			socket.onmessage = (event) => {
				const data = JSON.parse(event.data);
				if (data.type === 'doc_update' && data.delta && editor) {
					editor.updateContents(data.delta, 'silent');
				} else if (data.type === 'doc_saved' && data.updated_at) {
					lastSavedTime = data.updated_at;
					if (saveStatus === 'saving') {
						saveStatus = 'saved';
						setTimeout(() => {
							if (saveStatus === 'saved') saveStatus = 'idle';
						}, 2000);
					}
				}
			};

			socket.onclose = () => {
				console.log('WebSocket connection closed');
				saveStatus = 'error';
				toast.push('Connection lost. Please refresh the page.', {
					theme: {
						'--toastBackground': '#F56565',
						'--toastColor': 'white',
						'--toastBarBackground': '#C53030'
					}
				});
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
	function handleContentChange(detail: { delta: any; source: string }) {
		const { delta, source } = detail;
		if (source !== 'user') return;

		if (socket && socket.readyState === WebSocket.OPEN) {
			socket.send(JSON.stringify({ delta }));
		}
		// The `content` variable is already updated by the `bind:value` directive.
		// We just need to trigger the save.
		debouncedSave();
	}

	onDestroy(() => {
		if (socket) {
			// Prevent the onclose handler from firing when we navigate away
			socket.onclose = null;
			socket.close();
		}
		clearTimeout(debounceTimeout);
	});
</script>

<div class="page-container">
	<header class="header">
		<div class="header-left">
			<a href="/dashboard" class="logo-link" title="Back to Dashboard">
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
				<input
					type="text"
					bind:value={title}
					oninput={debouncedSave}
					class="doc-title-input"
					placeholder="Untitled Document"
				/>
				<div class="doc-status">{statusText}</div>
			</div>
		</div>
		<div class="header-right">
			{#if isOwner}
				<button
					onclick={() => (showShareModal = true)}
					class="share-button"
				>
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
			<QuillEditor bind:value={content} bind:editor onTextChange={handleContentChange} />
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
					<button onclick={handleAddCollaborator} class="add-button">Add</button>
				</div>
			{/if}

			<h3 class="collaborators-heading">Collaborators</h3>
			<ul class="collaborators-list">
				{#each collaborators as collaborator (collaborator.id)}
					<li class="collaborator-item">
						<div>
							<span>{collaborator.username}</span>
							<span class="collaborator-email">({collaborator.email})</span>
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
				<button onclick={confirmRemoveCollaborator} class="confirm-remove-button">
					Remove
				</button>
			</div>
		</div>
	</div>
{/if}

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
		box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04); /* shadow-2xl */
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
		box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04); /* shadow-xl */
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
</style>
