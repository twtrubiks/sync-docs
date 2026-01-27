<script lang="ts">
	import '../app.css';
	import { SvelteToast } from '@zerodevx/svelte-toast';
	import { isAuthenticated, logout, user, fetchCurrentUser } from '$lib/auth';
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import type { Snippet } from 'svelte';
	import { FileText, LayoutDashboard, LogIn, UserPlus, LogOut } from 'lucide-svelte';

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

<nav
	class="fixed left-2 right-2 top-4 z-50 mx-auto flex max-w-6xl items-center gap-2 rounded-xl border border-primary-200 bg-white/90 px-3 py-2.5 shadow-lg backdrop-blur-sm transition-all duration-200 sm:left-4 sm:right-4 sm:gap-6 sm:px-6 sm:py-3"
>
	<a
		href="/"
		class="flex items-center gap-1 text-primary-600 transition-colors duration-150 hover:text-primary-800 sm:gap-2"
	>
		<FileText size={20} strokeWidth={2} class="sm:hidden" />
		<FileText size={24} strokeWidth={2} class="hidden sm:block" />
		<span class="hidden font-semibold sm:inline">SyncDocs</span>
	</a>

	<!-- Svelte 5: $store auto-subscription still works for stores -->
	{#if $isAuthenticated}
		<a
			href="/dashboard"
			class="flex cursor-pointer items-center gap-1 text-primary-700 transition-colors duration-150 hover:text-primary-900 sm:gap-1.5"
			title="Dashboard"
		>
			<LayoutDashboard size={18} />
			<span class="hidden sm:inline">Dashboard</span>
		</a>
		<div class="flex-grow"></div>
		{#if $user}
			<span class="hidden text-sm text-primary-700 md:inline">歡迎, {$user.username}</span>
		{/if}
		<!-- Svelte 5: onclick instead of on:click -->
		<button
			onclick={handleLogout}
			class="flex cursor-pointer items-center gap-1 rounded-lg border-none bg-transparent px-2 py-1.5 text-primary-600 transition-all duration-150 hover:bg-primary-50 hover:text-primary-800 sm:gap-1.5 sm:px-3"
			title="Logout"
		>
			<LogOut size={18} />
			<span class="hidden sm:inline">Logout</span>
		</button>
	{:else}
		<div class="flex-grow"></div>
		<a
			href="/login"
			class="flex cursor-pointer items-center gap-1 text-primary-700 transition-colors duration-150 hover:text-primary-900 sm:gap-1.5"
			title="Login"
		>
			<LogIn size={18} />
			<span class="hidden sm:inline">Login</span>
		</a>
		<a
			href="/register"
			class="flex cursor-pointer items-center gap-1 rounded-lg bg-cta-500 px-2 py-1.5 font-medium text-white transition-all duration-150 hover:bg-cta-600 sm:gap-1.5 sm:px-4 sm:py-2"
			title="Register"
		>
			<UserPlus size={18} />
			<span class="hidden sm:inline">Register</span>
		</a>
	{/if}
</nav>

<main class="min-h-screen px-4 pt-24 pb-8">
	<!-- Svelte 5: {@render children()} instead of <slot /> -->
	{@render children()}
</main>

<SvelteToast />
