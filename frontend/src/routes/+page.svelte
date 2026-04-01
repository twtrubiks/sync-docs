<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAuthenticated } from '$lib/auth';
	import { browser } from '$app/environment';

	// Use onMount + subscribe for redirect logic
	// This ensures proper store subscription and cleanup
	onMount(() => {
		if (browser) {
			const unsubscribe = isAuthenticated.subscribe((loggedIn) => {
				if (loggedIn) {
					goto('/dashboard', { replaceState: true });
				} else {
					goto('/login', { replaceState: true });
				}
			});
			return unsubscribe;
		}
	});
</script>

<div class="flex h-screen items-center justify-center">
	<div class="text-primary-600 flex items-center gap-3">
		<div
			class="border-primary-200 border-t-primary-600 h-8 w-8 animate-spin rounded-full border-4"
		></div>
		<p class="text-lg">Loading...</p>
	</div>
</div>
