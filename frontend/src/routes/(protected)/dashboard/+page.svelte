<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { get, post, del, type User } from '$lib/auth';

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

	onMount(async () => {
		try {
			documents = await get('/documents/');
		} catch (error) {
			console.error('Failed to fetch documents:', error);
			// Optionally, show an error message to the user
		}
	});

	async function createNewDocument() {
		try {
			const newDocument = await post('/documents/', { title: 'Untitled Document' });
			await goto(`/docs/${newDocument.id}`);
		} catch (error) {
			console.error('Failed to create document:', error);
			// Optionally, show an error message to the user
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
			// Optionally, show an error message to the user
		}
	}
</script>

<div class="mx-auto mt-10 max-w-4xl">
	<div class="mb-6 flex items-center justify-between">
		<h1 class="text-3xl font-bold">Dashboard</h1>
		<!-- Svelte 5: onclick instead of on:click -->
		<button
			onclick={createNewDocument}
			class="rounded-md bg-blue-600 px-4 py-2 font-semibold text-white hover:bg-blue-700"
		>
			Create New Document
		</button>
	</div>
	<div class="rounded-lg bg-white shadow-md">
		<ul class="divide-y divide-gray-200">
			{#each documents as doc (doc.id)}
				<li class="flex items-center justify-between p-4 hover:bg-gray-50">
					<a href="/docs/{doc.id}" class="flex-grow text-lg text-blue-700 hover:underline"
						>{doc.title}</a
					>
					<div class="flex items-center">
						<span class="mr-4 text-sm text-gray-500">Owner: {doc.owner.username}</span>
						{#if !doc.is_owner && doc.permission}
							<span
								class="mr-4 rounded px-2 py-0.5 text-xs font-medium {doc.permission === 'write'
									? 'bg-green-100 text-green-800'
									: 'bg-indigo-100 text-indigo-800'}"
							>
								{doc.permission === 'write' ? 'Can Edit' : 'View Only'}
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
								class="ml-4 rounded-md bg-red-600 px-3 py-1 text-sm font-semibold text-white hover:bg-red-700"
							>
								Delete
							</button>
						{/if}
					</div>
				</li>
			{/each}
		</ul>
	</div>
</div>
