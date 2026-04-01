<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { post, del } from '$lib/auth';
	import { getDocuments, type Document } from '$lib/api/documents';
	import { Plus, FileText, Trash2, User as UserIcon, Eye, Pencil } from '@lucide/svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';

	// Svelte 5 Runes: use $state() for reactive state
	let documents = $state<Document[]>([]);
	let loading = $state(true);
	let currentPage = $state(1);
	let totalPages = $state(1);
	let total = $state(0);

	async function fetchDocuments(page: number = 1) {
		loading = true;
		try {
			const result = await getDocuments(page);
			documents = result.items;
			currentPage = result.page;
			totalPages = result.total_pages;
			total = result.total;
		} catch (error) {
			console.error('Failed to fetch documents:', error);
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		fetchDocuments();
	});

	async function createNewDocument() {
		try {
			const newDocument = await post('/documents/', { title: 'Untitled Document' });
			await goto(`/docs/${newDocument.id}`);
		} catch (error) {
			console.error('Failed to create document:', error);
		}
	}

	let showDeleteConfirm = $state(false);
	let pendingDeleteDocId = $state<string | null>(null);

	function deleteDocument(documentId: string) {
		pendingDeleteDocId = documentId;
		showDeleteConfirm = true;
	}

	async function confirmDeleteDocument() {
		if (!pendingDeleteDocId) return;
		const docId = pendingDeleteDocId;
		pendingDeleteDocId = null;

		try {
			await del(`/documents/${docId}/`);
			const targetPage = documents.length === 1 && currentPage > 1 ? currentPage - 1 : currentPage;
			await fetchDocuments(targetPage);
		} catch (error) {
			console.error('Failed to delete document:', error);
		}
	}
</script>

<div class="mx-auto max-w-4xl">
	<div class="mb-8 flex items-center justify-between">
		<div>
			<h1 class="text-primary-900 text-3xl font-bold">Dashboard</h1>
			<p class="text-primary-600 mt-1">Manage your documents</p>
		</div>
		<!-- Svelte 5: onclick instead of on:click -->
		<button
			onclick={createNewDocument}
			class="bg-cta-500 hover:bg-cta-600 flex cursor-pointer items-center gap-2 rounded-lg px-5 py-2.5 font-semibold text-white shadow-md transition-all duration-150 hover:shadow-lg"
		>
			<Plus size={20} />
			<span>New Document</span>
		</button>
	</div>

	<div class="border-primary-200 overflow-hidden rounded-xl border bg-white shadow-lg">
		{#if loading}
			<div class="flex items-center justify-center py-16">
				<div
					class="border-primary-200 border-t-primary-600 h-8 w-8 animate-spin rounded-full border-4"
				></div>
				<span class="text-primary-600 ml-3">Loading documents...</span>
			</div>
		{:else if documents.length === 0}
			<div class="py-16 text-center">
				<div
					class="bg-primary-100 mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full"
				>
					<FileText size={32} class="text-primary-400" />
				</div>
				<h3 class="text-primary-900 text-lg font-medium">No documents yet</h3>
				<p class="text-primary-600 mt-1">Create your first document to get started</p>
				<button
					onclick={createNewDocument}
					class="bg-primary-600 hover:bg-primary-700 mt-4 cursor-pointer rounded-lg px-4 py-2 font-medium text-white transition-colors"
				>
					Create Document
				</button>
			</div>
		{:else}
			<ul class="divide-primary-100 divide-y">
				{#each documents as doc (doc.id)}
					<li
						class="group hover:bg-primary-50 flex items-center justify-between p-5 transition-colors duration-150"
					>
						<a
							href="/docs/{doc.id}"
							class="text-primary-800 hover:text-primary-600 flex flex-grow cursor-pointer items-center gap-3 text-lg font-medium transition-colors"
						>
							<FileText size={20} class="text-primary-400" />
							{doc.title}
						</a>
						<div class="flex items-center gap-3">
							<span class="text-primary-500 flex items-center gap-1.5 text-sm">
								<UserIcon size={14} />
								{doc.owner.username}
							</span>
							{#if !doc.is_owner && doc.permission}
								<span
									class="flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium {doc.permission ===
									'write'
										? 'bg-emerald-100 text-emerald-700'
										: 'bg-primary-100 text-primary-700'}"
								>
									{#if doc.permission === 'write'}
										<Pencil size={12} />
										Can Edit
									{:else}
										<Eye size={12} />
										View Only
									{/if}
								</span>
							{/if}
							{#if doc.is_owner}
								<!-- Svelte 5: onclick with manual stopPropagation and preventDefault -->
								<button
									onclick={(e) => {
										e.stopPropagation();
										e.preventDefault();
										deleteDocument(doc.id);
									}}
									class="text-primary-400 cursor-pointer rounded-lg p-2 opacity-0 transition-all duration-150 group-hover:opacity-100 hover:bg-red-50 hover:text-red-600"
									title="Delete document"
								>
									<Trash2 size={18} />
								</button>
							{/if}
						</div>
					</li>
				{/each}
			</ul>

			<!-- 分頁控制 -->
			{#if totalPages > 1}
				<div class="border-primary-100 flex items-center justify-between border-t px-5 py-3">
					<span class="text-primary-500 text-sm">
						共 {total} 個文件
					</span>
					<div class="flex items-center gap-2">
						<button
							onclick={() => fetchDocuments(currentPage - 1)}
							disabled={currentPage <= 1}
							class="text-primary-700 hover:bg-primary-100 cursor-pointer rounded-lg px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40"
						>
							上一頁
						</button>
						<span class="text-primary-600 text-sm">
							{currentPage} / {totalPages}
						</span>
						<button
							onclick={() => fetchDocuments(currentPage + 1)}
							disabled={currentPage >= totalPages}
							class="text-primary-700 hover:bg-primary-100 cursor-pointer rounded-lg px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40"
						>
							下一頁
						</button>
					</div>
				</div>
			{/if}
		{/if}
	</div>
</div>

<ConfirmDialog
	bind:isOpen={showDeleteConfirm}
	title="刪除文件"
	message="確定要刪除這份文件嗎？此操作無法復原。"
	confirmText="刪除"
	variant="danger"
	onConfirm={confirmDeleteDocument}
	onCancel={() => {
		pendingDeleteDocId = null;
	}}
/>
