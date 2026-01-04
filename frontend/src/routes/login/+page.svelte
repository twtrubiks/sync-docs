<script lang="ts">
	import { token, fetchCurrentUser } from '$lib/auth';
	import { goto } from '$app/navigation';
	import { toast } from '@zerodevx/svelte-toast';

	// Svelte 5 Runes: use $state() for reactive state
	let username = $state('');
	let password = $state('');

	async function handleSubmit() {
		const response = await fetch('/api/token/pair', {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({ username: username, password: password })
		});

		if (response.ok) {
			const data = await response.json();
			token.set(data.access); // ninja-jwt returns { "access": "...", "refresh": "..." }
			await fetchCurrentUser();
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

<div class="mx-auto mt-10 max-w-md rounded-lg border border-gray-300 p-6 shadow-lg">
	<h1 class="mb-6 text-center text-2xl font-bold">Login</h1>
	<!-- Svelte 5: onsubmit instead of on:submit|preventDefault -->
	<form onsubmit={handleFormSubmit} class="space-y-4">
		<div>
			<label for="username" class="mb-1 block font-medium text-gray-700">Username</label>
			<input
				type="text"
				id="username"
				bind:value={username}
				required
				class="w-full rounded-md border border-gray-300 px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:outline-none"
			/>
		</div>
		<div>
			<label for="password" class="mb-1 block font-medium text-gray-700">Password</label>
			<input
				type="password"
				id="password"
				bind:value={password}
				required
				class="w-full rounded-md border border-gray-300 px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:outline-none"
			/>
		</div>
		<button
			type="submit"
			class="w-full rounded-md bg-blue-600 px-4 py-2 font-semibold text-white hover:bg-blue-700 focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:outline-none"
		>
			Login
		</button>
	</form>
</div>
