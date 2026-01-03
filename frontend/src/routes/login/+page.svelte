<script lang="ts">
  import { token } from '$lib/auth';
  import { goto } from '$app/navigation';
  import { toast } from '@zerodevx/svelte-toast';

  // Svelte 5 Runes: use $state() for reactive state
  let username = $state('');
  let password = $state('');

  async function handleSubmit() {
    const response = await fetch('/api/token/pair', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ username: username, password: password }),
    });

    if (response.ok) {
      const data = await response.json();
      token.set(data.access); // ninja-jwt returns { "access": "...", "refresh": "..." }
      goto('/dashboard');
    } else {
      // Handle error
      console.error('Login failed');
      toast.push('Login failed. Please check your credentials.', {
        theme: {
          '--toastBackground': '#F56565', // red-500
          '--toastColor': 'white',
          '--toastBarBackground': '#C53030' // red-700
        }
      });
    }
  }

  // Svelte 5: Wrapper to handle preventDefault manually
  function handleFormSubmit(e: SubmitEvent) {
    e.preventDefault();
    handleSubmit();
  }
</script>

<div class="max-w-md mx-auto mt-10 p-6 border border-gray-300 rounded-lg shadow-lg">
  <h1 class="text-2xl font-bold mb-6 text-center">Login</h1>
  <!-- Svelte 5: onsubmit instead of on:submit|preventDefault -->
  <form onsubmit={handleFormSubmit} class="space-y-4">
    <div>
      <label for="username" class="block mb-1 font-medium text-gray-700">Username</label>
      <input type="text" id="username" bind:value={username} required class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" />
    </div>
    <div>
      <label for="password" class="block mb-1 font-medium text-gray-700">Password</label>
      <input type="password" id="password" bind:value={password} required class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" />
    </div>
    <button type="submit" class="w-full py-2 px-4 bg-blue-600 text-white font-semibold rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500">
      Login
    </button>
  </form>
</div>
