<script lang="ts">
	import { processWithAI } from '$lib/ai';
	import { toast } from '@zerodevx/svelte-toast';
	import { X, Sparkles, FileText, Wand2, Check } from 'lucide-svelte';

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
		class="fixed top-1/2 left-1/2 z-50 flex max-h-[80vh] w-[600px] max-w-[90vw]
              -translate-x-1/2 -translate-y-1/2 flex-col rounded-xl border border-cta-200 bg-white shadow-2xl"
	>
		<!-- Header -->
		<div class="flex items-center justify-between border-b border-cta-100 p-4">
			<h2 class="flex items-center gap-2 text-lg font-semibold text-primary-900">
				<Sparkles size={20} class="text-cta-500" />
				AI 寫作助手
			</h2>
			<button
				class="cursor-pointer rounded-lg p-1.5 text-primary-400 transition-colors hover:bg-primary-100 hover:text-primary-600"
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
				<span class="mb-2 block text-sm font-medium text-primary-700">選取的文字</span>
				<div
					class="max-h-32 overflow-y-auto rounded-lg border border-primary-200 bg-primary-50 p-3 text-sm text-primary-700"
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
					<Wand2 size={18} />
					潤稿
				</button>
			</div>

			<!-- Result area -->
			{#if loading}
				<div class="flex items-center justify-center py-8">
					<div class="h-8 w-8 animate-spin rounded-full border-3 border-cta-200 border-t-cta-500"
					></div>
					<span class="ml-3 text-primary-600">AI 處理中...</span>
				</div>
			{:else if result}
				<div>
					<span class="mb-2 block text-sm font-medium text-primary-700">
						{actionLabels[currentAction!]}
					</span>
					<div
						class="max-h-48 overflow-y-auto whitespace-pre-wrap rounded-lg border border-cta-200 bg-cta-50 p-4 text-sm text-primary-800"
					>
						{result}
					</div>
				</div>
			{/if}
		</div>

		<!-- Footer buttons -->
		{#if result}
			<div class="flex justify-end gap-3 border-t border-primary-200 p-4">
				<button
					class="cursor-pointer rounded-lg border border-primary-300 px-4 py-2 font-medium text-primary-700 transition-colors hover:bg-primary-50"
					onclick={close}
				>
					取消
				</button>
				<button
					class="flex cursor-pointer items-center gap-2 rounded-lg bg-cta-500 px-4 py-2 font-medium text-white transition-colors hover:bg-cta-600"
					onclick={handleApply}
				>
					<Check size={18} />
					套用結果
				</button>
			</div>
		{/if}
	</div>
{/if}
