<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { isAuthenticated } from '$lib/auth';
  import { browser } from '$app/environment';

  onMount(() => {
    // We need to ensure this only runs on the client
    if (browser) {
      const unsubscribe = isAuthenticated.subscribe(loggedIn => {
        if (loggedIn) {
          goto('/dashboard', { replaceState: true });
        } else {
          goto('/login', { replaceState: true });
        }
      });

      // It's good practice to unsubscribe, though in this case,
      // the component is destroyed upon navigation anyway.
      return unsubscribe;
    }
  });
</script>

<div class="flex items-center justify-center h-screen">
  <p>Loading...</p>
</div>
