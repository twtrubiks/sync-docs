<script lang="ts">
  import '../app.css';
  import { SvelteToast } from '@zerodevx/svelte-toast';
  import { isAuthenticated, logout } from '$lib/auth';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import type { Snippet } from 'svelte';

  // Svelte 5 Runes: $props() with Snippet type for children
  let { children }: { children: Snippet } = $props();

  function handleLogout() {
    logout();
    goto('/login');
  }

  // Client-side route guard
  onMount(() => {
    const unsubscribe = page.subscribe((p) => {
      const isAuthRequired = p.route.id?.startsWith('/(protected)');
      if (isAuthRequired) {
        const authSub = isAuthenticated.subscribe(auth => {
          if (!auth) {
            goto('/login');
          }
        });
        // Unsubscribe from isAuthenticated to avoid memory leaks
        return () => authSub();
      }
    });

    return () => unsubscribe();
  });
</script>

<nav class="flex gap-4 p-4 bg-gray-100 border-b border-gray-300">
  <a href="/" class="text-gray-700 hover:text-blue-600">Home</a>
  <!-- Svelte 5: $store auto-subscription still works for stores -->
  {#if $isAuthenticated}
    <a href="/dashboard" class="text-gray-700 hover:text-blue-600">Dashboard</a>
    <!-- Svelte 5: onclick instead of on:click -->
    <button onclick={handleLogout} class="text-gray-700 hover:text-blue-600 p-0 bg-transparent border-none cursor-pointer">Logout</button>
  {:else}
    <a href="/login" class="text-gray-700 hover:text-blue-600">Login</a>
    <a href="/register" class="text-gray-700 hover:text-blue-600">Register</a>
  {/if}
</nav>

<main class="p-4">
  <!-- Svelte 5: {@render children()} instead of <slot /> -->
  {@render children()}
</main>

<SvelteToast />
