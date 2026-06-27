<script lang="ts">
	import { askWithAI } from '$lib/ai';
	import { toastError, toastWarning } from '$lib/toast';
	import { X, MessageCircleQuestion, Send } from '@lucide/svelte';

	let {
		isOpen = $bindable(false),
		documentText = ''
	}: {
		isOpen: boolean;
		documentText: string;
	} = $props();

	let question = $state('');
	let answer = $state('');
	let loading = $state(false);

	async function handleAsk() {
		if (!question.trim()) {
			toastWarning('請先輸入問題');
			return;
		}

		loading = true;
		answer = '';

		try {
			const response = await askWithAI(question, documentText);

			if (response.success && response.answer !== undefined) {
				answer = response.answer;
			} else {
				toastError(response.error || 'AI 問答失敗');
			}
		} catch (error: unknown) {
			if (error instanceof Error && error.name === 'AbortError') {
				toastError('Request timed out, please try again');
			} else {
				toastError('AI processing request failed');
			}
		} finally {
			loading = false;
		}
	}

	function close() {
		isOpen = false;
		question = '';
		answer = '';
	}

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
				<MessageCircleQuestion size={20} class="text-cta-500" />
				文件問答
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
			<!-- 問題輸入 -->
			<div>
				<span class="text-primary-700 mb-2 block text-sm font-medium">針對整份文件提問</span>
				<textarea
					bind:value={question}
					rows="3"
					placeholder="例如：這份文件的重點是什麼？"
					class="border-primary-200 focus:border-cta-400 text-primary-800 w-full resize-none rounded-lg border p-3 text-sm focus:outline-none"
				></textarea>
				<button
					class="bg-cta-500 hover:bg-cta-600 mt-2 flex cursor-pointer items-center gap-2 rounded-lg px-4 py-2 font-medium text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50"
					onclick={handleAsk}
					disabled={loading || !question.trim()}
				>
					<Send size={16} />
					送出
				</button>
			</div>

			<!-- 答案 -->
			{#if loading}
				<div class="flex items-center justify-center py-8">
					<div
						class="border-cta-200 border-t-cta-500 h-8 w-8 animate-spin rounded-full border-3"
					></div>
					<span class="text-primary-600 ml-3">AI 回答中...</span>
				</div>
			{:else if answer}
				<div>
					<span class="text-primary-700 mb-2 block text-sm font-medium">回答</span>
					<div
						class="border-cta-200 bg-cta-50 text-primary-800 max-h-64 overflow-y-auto rounded-lg border p-4 text-sm whitespace-pre-wrap"
					>
						{answer}
					</div>
				</div>
			{/if}
		</div>
	</div>
{/if}
