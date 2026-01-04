<script lang="ts">
	import { goto } from '$app/navigation';
	import { toast } from '@zerodevx/svelte-toast';

	// Svelte 5 Runes: use $state() for reactive state
	let username = $state('');
	let email = $state('');
	let password = $state('');
	let confirmPassword = $state('');

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
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				username,
				password,
				...(email.trim() && { email: email.trim() })
			})
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
			const errorData = await response
				.json()
				.catch(() => ({ detail: 'An unknown error occurred.' }));
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

	// Svelte 5: Wrapper to handle preventDefault manually
	function handleFormSubmit(e: SubmitEvent) {
		e.preventDefault();
		handleSubmit();
	}
</script>

<div class="mx-auto mt-10 max-w-md rounded-lg border border-gray-300 p-6 shadow-lg">
	<h1 class="mb-6 text-center text-2xl font-bold">Register</h1>
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
			<label for="email" class="mb-1 block font-medium text-gray-700">
				Email <span class="text-sm font-normal text-gray-400">(optional)</span>
			</label>
			<input
				type="email"
				id="email"
				bind:value={email}
				placeholder="your@email.com"
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
		<div>
			<label for="confirm-password" class="mb-1 block font-medium text-gray-700"
				>Confirm Password</label
			>
			<input
				type="password"
				id="confirm-password"
				bind:value={confirmPassword}
				required
				class="w-full rounded-md border border-gray-300 px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:outline-none"
			/>
		</div>
		<button
			type="submit"
			class="w-full rounded-md bg-green-600 px-4 py-2 font-semibold text-white hover:bg-green-700 focus:ring-2 focus:ring-green-500 focus:ring-offset-2 focus:outline-none"
		>
			Register
		</button>
	</form>
</div>
