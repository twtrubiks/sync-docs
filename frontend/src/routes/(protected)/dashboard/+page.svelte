<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { get, post, del, type User } from '$lib/auth';
	import { Plus, FileText, Trash2, User as UserIcon, Eye, Pencil } from 'lucide-svelte';

	interface Document {
		id: string; // Changed from number to string for UUID
		title: string;
		is_owner: boolean;
		owner: User;
		permission: 'read' | 'write' | null; // User's permission level for shared docs
		can_write: boolean; // Whether user can edit
	}

	// Svelte 5 Runes: use $state() for reactive state
	let documents = $state<Document[]>([]);
	let loading = $state(true);

	onMount(async () => {
		try {
			documents = await get('/documents/');
		} catch (error) {
			console.error('Failed to fetch documents:', error);
		} finally {
			loading = false;
		}
	});

	async function createNewDocument() {
		try {
			const newDocument = await post('/documents/', { title: 'Untitled Document' });
			await goto(`/docs/${newDocument.id}`);
		} catch (error) {
			console.error('Failed to create document:', error);
		}
	}

	async function deleteDocument(documentId: string) {
		if (!confirm('Are you sure you want to delete this document?')) {
			return;
		}
		try {
			await del(`/documents/${documentId}/`);
			documents = documents.filter((doc) => doc.id !== documentId);
		} catch (error) {
			console.error('Failed to delete document:', error);
		}
	}
</script>

<div class="mx-auto max-w-4xl">
	<div class="mb-8 flex items-center justify-between">
		<div>
			<h1 class="text-3xl font-bold text-primary-900">Dashboard</h1>
			<p class="mt-1 text-primary-600">Manage your documents</p>
		</div>
		<!-- Svelte 5: onclick instead of on:click -->
		<button
			onclick={createNewDocument}
			class="flex cursor-pointer items-center gap-2 rounded-lg bg-cta-500 px-5 py-2.5 font-semibold text-white shadow-md transition-all duration-150 hover:bg-cta-600 hover:shadow-lg"
		>
			<Plus size={20} />
			<span>New Document</span>
		</button>
	</div>

	<div class="overflow-hidden rounded-xl border border-primary-200 bg-white shadow-lg">
		{#if loading}
			<div class="flex items-center justify-center py-16">
				<div
					class="h-8 w-8 animate-spin rounded-full border-4 border-primary-200 border-t-primary-600"
				></div>
				<span class="ml-3 text-primary-600">Loading documents...</span>
			</div>
		{:else if documents.length === 0}
			<div class="py-16 text-center">
				<div
					class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-primary-100"
				>
					<FileText size={32} class="text-primary-400" />
				</div>
				<h3 class="text-lg font-medium text-primary-900">No documents yet</h3>
				<p class="mt-1 text-primary-600">Create your first document to get started</p>
				<button
					onclick={createNewDocument}
					class="mt-4 cursor-pointer rounded-lg bg-primary-600 px-4 py-2 font-medium text-white transition-colors hover:bg-primary-700"
				>
					Create Document
				</button>
			</div>
		{:else}
			<ul class="divide-y divide-primary-100">
				{#each documents as doc (doc.id)}
					<li
						class="group flex items-center justify-between p-5 transition-colors duration-150 hover:bg-primary-50"
					>
						<a
							href="/docs/{doc.id}"
							class="flex flex-grow cursor-pointer items-center gap-3 text-lg font-medium text-primary-800 transition-colors hover:text-primary-600"
						>
							<FileText size={20} class="text-primary-400" />
							{doc.title}
						</a>
						<div class="flex items-center gap-3">
							<span class="flex items-center gap-1.5 text-sm text-primary-500">
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
									class="cursor-pointer rounded-lg p-2 text-primary-400 opacity-0 transition-all duration-150 hover:bg-red-50 hover:text-red-600 group-hover:opacity-100"
									title="Delete document"
								>
									<Trash2 size={18} />
								</button>
							{/if}
						</div>
					</li>
				{/each}
			</ul>
		{/if}
	</div>
</div>
