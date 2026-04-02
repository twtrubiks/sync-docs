<script lang="ts">
	import { token, refreshToken, fetchCurrentUser, publicPost } from '$lib/auth';
	import { goto } from '$app/navigation';
	import { toastError } from '$lib/toast';
	import { LogIn, User, Lock } from '@lucide/svelte';

	// Svelte 5 Runes: use $state() for reactive state
	let username = $state('');
	let password = $state('');
	let isLoading = $state(false);

	async function handleSubmit() {
		isLoading = true;
		try {
			const response = await publicPost('/token/pair', { username, password });

			if (response.ok) {
				const data = await response.json();
				token.set(data.access);
				refreshToken.set(data.refresh);
				await fetchCurrentUser();
				goto('/dashboard');
			} else {
				// Handle error
				console.error('Login failed');
				toastError('Login failed. Please check your credentials.');
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
	<div class="border-primary-200 rounded-2xl border bg-white p-8 shadow-xl">
		<div class="mb-8 text-center">
			<div
				class="bg-primary-100 mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full"
			>
				<LogIn size={32} class="text-primary-600" />
			</div>
			<h1 class="text-primary-900 text-2xl font-bold">Welcome Back</h1>
			<p class="text-primary-600 mt-2">Sign in to continue to SyncDocs</p>
		</div>

		<!-- Svelte 5: onsubmit instead of on:submit|preventDefault -->
		<form onsubmit={handleFormSubmit} class="space-y-5">
			<div>
				<label for="username" class="text-primary-800 mb-2 block text-sm font-medium">
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
						placeholder="Enter your username"
						class="border-primary-300 focus:border-primary-500 focus:ring-primary-500/20 w-full cursor-text rounded-lg border py-3 pr-4 pl-10 transition-all duration-150 focus:ring-2 focus:outline-none"
					/>
				</div>
			</div>
			<div>
				<label for="password" class="text-primary-800 mb-2 block text-sm font-medium">
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
						placeholder="Enter your password"
						class="border-primary-300 focus:border-primary-500 focus:ring-primary-500/20 w-full cursor-text rounded-lg border py-3 pr-4 pl-10 transition-all duration-150 focus:ring-2 focus:outline-none"
					/>
				</div>
			</div>
			<button
				type="submit"
				disabled={isLoading}
				class="bg-primary-600 hover:bg-primary-700 focus:ring-primary-500 flex w-full cursor-pointer items-center justify-center gap-2 rounded-lg px-4 py-3 font-semibold text-white transition-all duration-150 focus:ring-2 focus:ring-offset-2 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
			>
				{#if isLoading}
					<span class="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent"
					></span>
					<span>Signing in...</span>
				{:else}
					<LogIn size={20} />
					<span>Sign In</span>
				{/if}
			</button>
		</form>

		<p class="text-primary-600 mt-6 text-center text-sm">
			Don't have an account?
			<a
				href="/register"
				class="text-cta-500 hover:text-cta-600 cursor-pointer font-medium transition-colors"
			>
				Create one
			</a>
		</p>
	</div>
</div>
