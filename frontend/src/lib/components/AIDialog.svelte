<script lang="ts">
	import { processWithAI } from '$lib/ai';
	import { toastError, toastWarning } from '$lib/toast';
	import { X, Sparkles, FileText, WandSparkles, Check } from '@lucide/svelte';

	let {
		isOpen = $bindable(false),
		selectedText = '',
		onApply = (_text: string) => {}
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
			toastWarning('Please select text first');
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
				toastError(response.error || 'AI processing failed');
			}
		} catch (error: unknown) {
			// Handle timeout and other errors
			if (error instanceof Error && error.name === 'AbortError') {
				toastError('Request timed out, please try again');
			} else {
				toastError('AI processing request failed');
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

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && isOpen) {
			close();
		}
	}
</script>

<svelte:window onkeydown={handleKeydown} />

{#if isOpen}
	<!-- Background overlay -->
	<button
		type="button"
		class="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm"
		onclick={close}
		aria-label="關閉對話框"
	></button>

	<!-- Dialog -->
	<div
		class="border-cta-200 fixed top-1/2 left-1/2 z-50 flex max-h-[80vh] w-[600px]
              max-w-[90vw] -translate-x-1/2 -translate-y-1/2 flex-col rounded-xl border bg-white shadow-2xl"
	>
		<!-- Header -->
		<div class="border-cta-100 flex items-center justify-between border-b p-4">
			<h2 class="text-primary-900 flex items-center gap-2 text-lg font-semibold">
				<Sparkles size={20} class="text-cta-500" />
				AI 寫作助手
			</h2>
			<button
				class="text-primary-400 hover:bg-primary-100 hover:text-primary-600 cursor-pointer rounded-lg p-1.5 transition-colors"
				onclick={close}
				aria-label="Close dialog"
			>
				<X size={20} />
			</button>
		</div>

		<!-- Content area -->
		<div class="flex-1 space-y-4 overflow-y-auto p-5">
			<!-- Selected text -->
			<div>
				<span class="text-primary-700 mb-2 block text-sm font-medium">選取的文字</span>
				<div
					class="border-primary-200 bg-primary-50 text-primary-700 max-h-32 overflow-y-auto rounded-lg border p-3 text-sm"
				>
					{selectedText || '（未選取文字）'}
				</div>
			</div>

			<!-- Action buttons -->
			<div class="flex gap-3">
				<button
					class="flex flex-1 cursor-pointer items-center justify-center gap-2 rounded-lg border-2 px-4 py-3 font-medium transition-all duration-150
                 {currentAction === 'summarize'
						? 'border-cta-500 bg-cta-50 text-cta-700'
						: 'border-primary-200 text-primary-600 hover:border-cta-300 hover:bg-cta-50'}
                 disabled:cursor-not-allowed disabled:opacity-50"
					onclick={() => handleAction('summarize')}
					disabled={loading || !selectedText.trim()}
				>
					<FileText size={18} />
					摘要
				</button>
				<button
					class="flex flex-1 cursor-pointer items-center justify-center gap-2 rounded-lg border-2 px-4 py-3 font-medium transition-all duration-150
                 {currentAction === 'polish'
						? 'border-cta-500 bg-cta-50 text-cta-700'
						: 'border-primary-200 text-primary-600 hover:border-cta-300 hover:bg-cta-50'}
                 disabled:cursor-not-allowed disabled:opacity-50"
					onclick={() => handleAction('polish')}
					disabled={loading || !selectedText.trim()}
				>
					<WandSparkles size={18} />
					潤稿
				</button>
			</div>

			<!-- Result area -->
			{#if loading}
				<div class="flex items-center justify-center py-8">
					<div
						class="border-cta-200 border-t-cta-500 h-8 w-8 animate-spin rounded-full border-3"
					></div>
					<span class="text-primary-600 ml-3">AI 處理中...</span>
				</div>
			{:else if result}
				<div>
					<span class="text-primary-700 mb-2 block text-sm font-medium">
						{actionLabels[currentAction!]}
					</span>
					<div
						class="border-cta-200 bg-cta-50 text-primary-800 max-h-48 overflow-y-auto rounded-lg border p-4 text-sm whitespace-pre-wrap"
					>
						{result}
					</div>
				</div>
			{/if}
		</div>

		<!-- Footer buttons -->
		{#if result}
			<div class="border-primary-200 flex justify-end gap-3 border-t p-4">
				<button
					class="border-primary-300 text-primary-700 hover:bg-primary-50 cursor-pointer rounded-lg border px-4 py-2 font-medium transition-colors"
					onclick={close}
				>
					取消
				</button>
				<button
					class="bg-cta-500 hover:bg-cta-600 flex cursor-pointer items-center gap-2 rounded-lg px-4 py-2 font-medium text-white transition-colors"
					onclick={handleApply}
				>
					<Check size={18} />
					套用結果
				</button>
			</div>
		{/if}
	</div>
{/if}
