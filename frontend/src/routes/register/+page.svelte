<script lang="ts">
	import { goto } from '$app/navigation';
	import { toastSuccess, toastError } from '$lib/toast';
	import { UserPlus, User, Mail, Lock, ShieldCheck } from 'lucide-svelte';

	// Svelte 5 Runes: use $state() for reactive state
	let username = $state('');
	let email = $state('');
	let password = $state('');
	let confirmPassword = $state('');
	let isLoading = $state(false);

	async function handleSubmit() {
		if (password !== confirmPassword) {
			toastError('Passwords do not match');
			return;
		}

		isLoading = true;
		try {
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
				toastSuccess('Registration successful! Please log in.');
				goto('/login');
			} else {
				// Handle error
				const errorData = await response
					.json()
					.catch(() => ({ detail: 'An unknown error occurred.' }));
				console.error('Registration failed:', errorData);
				const message = errorData.detail || JSON.stringify(errorData);
				toastError(`Registration failed: ${message}`);
			}
		} finally {
			isLoading = false;
		}
	}

	// Svelte 5: Wrapper to handle preventDefault manually
	function handleFormSubmit(e: SubmitEvent) {
		e.preventDefault();
		handleSubmit();
	}
</script>

<div class="mx-auto mt-8 max-w-md">
	<div class="rounded-2xl border border-primary-200 bg-white p-8 shadow-xl">
		<div class="mb-8 text-center">
			<div
				class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-cta-100"
			>
				<UserPlus size={32} class="text-cta-500" />
			</div>
			<h1 class="text-2xl font-bold text-primary-900">Create Account</h1>
			<p class="mt-2 text-primary-600">Join SyncDocs and start collaborating</p>
		</div>

		<!-- Svelte 5: onsubmit instead of on:submit|preventDefault -->
		<form onsubmit={handleFormSubmit} class="space-y-5">
			<div>
				<label for="username" class="mb-2 block text-sm font-medium text-primary-800">
					Username
				</label>
				<div class="relative">
					<div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
						<User size={18} class="text-primary-400" />
					</div>
					<input
						type="text"
						id="username"
						bind:value={username}
						required
						placeholder="Choose a username"
						class="w-full cursor-text rounded-lg border border-primary-300 py-3 pr-4 pl-10 transition-all duration-150 focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none"
					/>
				</div>
			</div>
			<div>
				<label for="email" class="mb-2 block text-sm font-medium text-primary-800">
					Email <span class="font-normal text-primary-400">(optional)</span>
				</label>
				<div class="relative">
					<div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
						<Mail size={18} class="text-primary-400" />
					</div>
					<input
						type="email"
						id="email"
						bind:value={email}
						placeholder="your@email.com"
						class="w-full cursor-text rounded-lg border border-primary-300 py-3 pr-4 pl-10 transition-all duration-150 focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none"
					/>
				</div>
			</div>
			<div>
				<label for="password" class="mb-2 block text-sm font-medium text-primary-800">
					Password
				</label>
				<div class="relative">
					<div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
						<Lock size={18} class="text-primary-400" />
					</div>
					<input
						type="password"
						id="password"
						bind:value={password}
						required
						placeholder="Create a password"
						class="w-full cursor-text rounded-lg border border-primary-300 py-3 pr-4 pl-10 transition-all duration-150 focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none"
					/>
				</div>
			</div>
			<div>
				<label for="confirm-password" class="mb-2 block text-sm font-medium text-primary-800">
					Confirm Password
				</label>
				<div class="relative">
					<div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
						<ShieldCheck size={18} class="text-primary-400" />
					</div>
					<input
						type="password"
						id="confirm-password"
						bind:value={confirmPassword}
						required
						placeholder="Confirm your password"
						class="w-full cursor-text rounded-lg border border-primary-300 py-3 pr-4 pl-10 transition-all duration-150 focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none"
					/>
				</div>
			</div>
			<button
				type="submit"
				disabled={isLoading}
				class="flex w-full cursor-pointer items-center justify-center gap-2 rounded-lg bg-cta-500 px-4 py-3 font-semibold text-white transition-all duration-150 hover:bg-cta-600 focus:ring-2 focus:ring-cta-500 focus:ring-offset-2 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
			>
				{#if isLoading}
					<span class="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent"
					></span>
					<span>Creating account...</span>
				{:else}
					<UserPlus size={20} />
					<span>Create Account</span>
				{/if}
			</button>
		</form>

		<p class="mt-6 text-center text-sm text-primary-600">
			Already have an account?
			<a
				href="/login"
				class="cursor-pointer font-medium text-primary-600 transition-colors hover:text-primary-800"
			>
				Sign in
			</a>
		</p>
	</div>
</div>
