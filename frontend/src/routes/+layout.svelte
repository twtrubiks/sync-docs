<script lang="ts">
	import '../app.css';
	import { SvelteToast } from '@zerodevx/svelte-toast';
	import { isAuthenticated, logout, user, fetchCurrentUser } from '$lib/auth';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import type { Snippet } from 'svelte';
	import { FileText, LayoutDashboard, LogIn, UserPlus, LogOut } from '@lucide/svelte';

	let { children }: { children: Snippet } = $props();

	function handleLogout() {
		logout();
		goto('/login');
	}

	// Fetch user info if authenticated but user data not yet loaded (e.g. page refresh)
	$effect(() => {
		if ($isAuthenticated && !$user) {
			fetchCurrentUser();
		}
	});

	// Client-side route guard
	$effect(() => {
		const isAuthRequired = $page.route.id?.startsWith('/(protected)');
		if (isAuthRequired && !$isAuthenticated) {
			goto('/login');
		}
	});
</script>

<nav
	class="border-primary-200 fixed top-4 right-2 left-2 z-50 mx-auto flex max-w-6xl items-center gap-2 rounded-xl border bg-white/90 px-3 py-2.5 shadow-lg backdrop-blur-sm transition-all duration-200 sm:right-4 sm:left-4 sm:gap-6 sm:px-6 sm:py-3"
>
	<a
		href="/"
		class="text-primary-600 hover:text-primary-800 flex items-center gap-1 transition-colors duration-150 sm:gap-2"
	>
		<FileText size={20} strokeWidth={2} class="sm:hidden" />
		<FileText size={24} strokeWidth={2} class="hidden sm:block" />
		<span class="hidden font-semibold sm:inline">SyncDocs</span>
	</a>

	{#if $isAuthenticated}
		<a
			href="/dashboard"
			class="text-primary-700 hover:text-primary-900 flex cursor-pointer items-center gap-1 transition-colors duration-150 sm:gap-1.5"
			title="Dashboard"
		>
			<LayoutDashboard size={18} />
			<span class="hidden sm:inline">Dashboard</span>
		</a>
		<div class="flex-grow"></div>
		{#if $user}
			<span class="text-primary-700 hidden text-sm md:inline">歡迎, {$user.username}</span>
		{/if}
		<button
			onclick={handleLogout}
			class="text-primary-600 hover:bg-primary-50 hover:text-primary-800 flex cursor-pointer items-center gap-1 rounded-lg border-none bg-transparent px-2 py-1.5 transition-all duration-150 sm:gap-1.5 sm:px-3"
			title="Logout"
		>
			<LogOut size={18} />
			<span class="hidden sm:inline">Logout</span>
		</button>
	{:else}
		<div class="flex-grow"></div>
		<a
			href="/login"
			class="text-primary-700 hover:text-primary-900 flex cursor-pointer items-center gap-1 transition-colors duration-150 sm:gap-1.5"
			title="Login"
		>
			<LogIn size={18} />
			<span class="hidden sm:inline">Login</span>
		</a>
		<a
			href="/register"
			class="bg-cta-500 hover:bg-cta-600 flex cursor-pointer items-center gap-1 rounded-lg px-2 py-1.5 font-medium text-white transition-all duration-150 sm:gap-1.5 sm:px-4 sm:py-2"
			title="Register"
		>
			<UserPlus size={18} />
			<span class="hidden sm:inline">Register</span>
		</a>
	{/if}
</nav>

<main class="min-h-screen px-4 pt-24 pb-8">
	{@render children()}
</main>

<SvelteToast />
