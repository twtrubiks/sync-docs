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
	<p>Loading...</p>
</div>
