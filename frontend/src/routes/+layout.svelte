<script lang="ts">
	import '../app.css';
	import { SvelteToast } from '@zerodevx/svelte-toast';
	import { isAuthenticated, logout, user, fetchCurrentUser } from '$lib/auth';
	import { browser } from '$app/environment';
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

	// Fetch user info on mount if authenticated (handles page refresh)
	onMount(() => {
		if (browser && $isAuthenticated && !$user) {
			fetchCurrentUser();
		}
	});

	// Client-side route guard
	onMount(() => {
		const unsubscribe = page.subscribe((p) => {
			const isAuthRequired = p.route.id?.startsWith('/(protected)');
			if (isAuthRequired) {
				const authSub = isAuthenticated.subscribe((auth) => {
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

<nav class="flex gap-4 border-b border-gray-300 bg-gray-100 p-4">
	<a href="/" class="text-gray-700 hover:text-blue-600">Home</a>
	<!-- Svelte 5: $store auto-subscription still works for stores -->
	{#if $isAuthenticated}
		<a href="/dashboard" class="text-gray-700 hover:text-blue-600">Dashboard</a>
		<div class="flex-grow"></div>
		{#if $user}
			<span class="text-gray-700">歡迎, {$user.username}</span>
		{/if}
		<!-- Svelte 5: onclick instead of on:click -->
		<button
			onclick={handleLogout}
			class="cursor-pointer border-none bg-transparent p-0 text-gray-700 hover:text-blue-600"
			>Logout</button
		>
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
