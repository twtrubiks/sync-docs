<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { get, post, del } from '$lib/auth';

  interface Document {
    id: string; // Changed from number to string for UUID
    title: string;
    is_owner: boolean;
    owner: {
      id: number;
      username: string;
      email: string;
    };
  }

  let documents: Document[] = [];

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
      documents = documents.filter(doc => doc.id !== documentId);
    } catch (error) {
      console.error('Failed to delete document:', error);
      // Optionally, show an error message to the user
    }
  }
</script>

<div class="max-w-4xl mx-auto mt-10">
  <div class="flex justify-between items-center mb-6">
    <h1 class="text-3xl font-bold">Dashboard</h1>
    <button on:click={createNewDocument} class="py-2 px-4 bg-blue-600 text-white font-semibold rounded-md hover:bg-blue-700">
      Create New Document
    </button>
  </div>
  <div class="bg-white shadow-md rounded-lg">
    <ul class="divide-y divide-gray-200">
      {#each documents as doc (doc.id)}
        <li class="p-4 hover:bg-gray-50 flex justify-between items-center">
          <a href="/docs/{doc.id}" class="text-lg text-blue-700 hover:underline flex-grow">{doc.title}</a>
          <div class="flex items-center">
            <span class="text-sm text-gray-500 mr-4">Owner: {doc.owner.username}</span>
            {#if doc.is_owner}
              <button
              on:click|stopPropagation={(e) => { e.preventDefault(); deleteDocument(doc.id); }}
              class="py-1 px-3 bg-red-600 text-white font-semibold rounded-md hover:bg-red-700 text-sm ml-4"
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
