<script lang="ts">
	import { processWithAI } from '$lib/ai';
	import { toast } from '@zerodevx/svelte-toast';

	let {
		isOpen = $bindable(false),
		selectedText = '',
		onApply = (text: string) => {}
	}: {
		isOpen: boolean;
		selectedText: string;
		onApply: (text: string) => void;
	} = $props();

	let loading = $state(false);
	let result = $state('');
	let currentAction = $state<'summarize' | 'polish' | null>(null);

	async function handleAction(action: 'summarize' | 'polish') {
		if (!selectedText.trim()) {
			toast.push('Please select text first', { theme: { '--toastBackground': '#f59e0b' } });
			return;
		}

		loading = true;
		currentAction = action;
		result = '';

		try {
			const response = await processWithAI({ action, text: selectedText });

			if (response.success) {
				result = response.result;
			} else {
				toast.push(response.error || 'AI processing failed', {
					theme: { '--toastBackground': '#ef4444' }
				});
			}
		} catch (error: unknown) {
			// Handle timeout and other errors
			if (error instanceof Error && error.name === 'AbortError') {
				toast.push('Request timed out, please try again', {
					theme: { '--toastBackground': '#ef4444' }
				});
			} else {
				toast.push('AI processing request failed', { theme: { '--toastBackground': '#ef4444' } });
			}
		} finally {
			loading = false;
		}
	}

	function handleApply() {
		if (result) {
			onApply(result);
			close();
		}
	}

	function close() {
		isOpen = false;
		result = '';
		currentAction = null;
	}

	const actionLabels = {
		summarize: '摘要結果',
		polish: '潤稿結果'
	};
</script>

{#if isOpen}
	<!-- Background overlay -->
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="fixed inset-0 bg-black/50 z-50" onclick={close}></div>

	<!-- Dialog -->
	<div
		class="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2
              w-[600px] max-w-[90vw] max-h-[80vh] bg-white rounded-lg shadow-xl z-50
              flex flex-col"
	>
		<!-- Header -->
		<div class="p-4 border-b flex items-center justify-between">
			<h2 class="text-lg font-semibold flex items-center gap-2">
				<svg
					class="w-5 h-5 text-purple-600"
					fill="none"
					stroke="currentColor"
					viewBox="0 0 24 24"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
					/>
				</svg>
				AI 寫作助手
			</h2>
			<button class="text-gray-500 hover:text-gray-700" onclick={close} aria-label="Close dialog">
				<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M6 18L18 6M6 6l12 12"
					/>
				</svg>
			</button>
		</div>

		<!-- Content area -->
		<div class="flex-1 overflow-y-auto p-4 space-y-4">
			<!-- Selected text -->
			<div>
				<span class="block text-sm font-medium text-gray-700 mb-1">選取的文字</span>
				<div class="p-3 bg-gray-50 rounded-lg text-sm text-gray-600 max-h-32 overflow-y-auto">
					{selectedText || '（未選取文字）'}
				</div>
			</div>

			<!-- Action buttons -->
			<div class="flex gap-2">
				<button
					class="flex-1 py-2 px-4 rounded-lg border-2 transition-colors
                 {currentAction === 'summarize'
						? 'border-purple-600 bg-purple-50'
						: 'border-gray-200 hover:border-purple-300'}
                 disabled:opacity-50"
					onclick={() => handleAction('summarize')}
					disabled={loading || !selectedText.trim()}
				>
					摘要
				</button>
				<button
					class="flex-1 py-2 px-4 rounded-lg border-2 transition-colors
                 {currentAction === 'polish'
						? 'border-purple-600 bg-purple-50'
						: 'border-gray-200 hover:border-purple-300'}
                 disabled:opacity-50"
					onclick={() => handleAction('polish')}
					disabled={loading || !selectedText.trim()}
				>
					潤稿
				</button>
			</div>

			<!-- Result area -->
			{#if loading}
				<div class="flex items-center justify-center py-8">
					<div class="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600"></div>
					<span class="ml-3 text-gray-600">AI 處理中...</span>
				</div>
			{:else if result}
				<div>
					<span class="block text-sm font-medium text-gray-700 mb-1">
						{actionLabels[currentAction!]}
					</span>
					<div
						class="p-3 bg-purple-50 rounded-lg text-sm whitespace-pre-wrap max-h-48 overflow-y-auto"
					>
						{result}
					</div>
				</div>
			{/if}
		</div>

		<!-- Footer buttons -->
		{#if result}
			<div class="p-4 border-t flex justify-end gap-2">
				<button
					class="py-2 px-4 rounded-lg border border-gray-300 hover:bg-gray-50 transition-colors"
					onclick={close}
				>
					取消
				</button>
				<button
					class="py-2 px-4 rounded-lg bg-purple-600 text-white hover:bg-purple-700 transition-colors"
					onclick={handleApply}
				>
					套用結果
				</button>
			</div>
		{/if}
	</div>
{/if}
