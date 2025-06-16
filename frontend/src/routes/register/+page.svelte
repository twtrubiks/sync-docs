<script lang="ts">
  import { goto } from '$app/navigation';
  import { toast } from '@zerodevx/svelte-toast';

  let username = '';
  let password = '';
  let confirmPassword = '';

  async function handleSubmit() {
    if (password !== confirmPassword) {
      toast.push('Passwords do not match', {
        theme: {
          '--toastBackground': '#F56565', // red-500
          '--toastColor': 'white',
          '--toastBarBackground': '#C53030' // red-700
        }
      });
      return;
    }

    const response = await fetch('/api/auth/register', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ username, password }),
    });

    if (response.ok) {
      toast.push('Registration successful! Please log in.', {
        theme: {
          '--toastBackground': '#48BB78', // green-500
          '--toastColor': 'white',
          '--toastBarBackground': '#2F855A' // green-700
        }
      });
      goto('/login');
    } else {
      // Handle error
      const errorData = await response.json().catch(() => ({ detail: 'An unknown error occurred.' }));
      console.error('Registration failed:', errorData);
      const message = errorData.detail || JSON.stringify(errorData);
      toast.push(`Registration failed: ${message}`, {
        theme: {
          '--toastBackground': '#F56565', // red-500
          '--toastColor': 'white',
          '--toastBarBackground': '#C53030' // red-700
        }
      });
    }
  }
</script>

<div class="max-w-md mx-auto mt-10 p-6 border border-gray-300 rounded-lg shadow-lg">
  <h1 class="text-2xl font-bold mb-6 text-center">Register</h1>
  <form on:submit|preventDefault={handleSubmit} class="space-y-4">
    <div>
      <label for="username" class="block mb-1 font-medium text-gray-700">Username</label>
      <input type="text" id="username" bind:value={username} required class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" />
    </div>
    <div>
      <label for="password" class="block mb-1 font-medium text-gray-700">Password</label>
      <input type="password" id="password" bind:value={password} required class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" />
    </div>
    <div>
      <label for="confirm-password" class="block mb-1 font-medium text-gray-700">Confirm Password</label>
      <input type="password" id="confirm-password" bind:value={confirmPassword} required class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" />
    </div>
    <button type="submit" class="w-full py-2 px-4 bg-green-600 text-white font-semibold rounded-md hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500">
      Register
    </button>
  </form>
</div>
