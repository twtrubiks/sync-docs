<script lang="ts">
	import { metadataWithAI, type DocumentMetadata } from '$lib/ai';
	import { toastError } from '$lib/toast';
	import { X, ScanText, Tag, Languages, Clock } from '@lucide/svelte';

	let {
		isOpen = $bindable(false),
		documentText = ''
	}: {
		isOpen: boolean;
		documentText: string;
	} = $props();

	let loading = $state(false);
	let result = $state<DocumentMetadata | null>(null);

	// 已分析過的文字，避免同一份內容重複打 API
	let analyzedText = $state<string | null>(null);

	// 開啟時自動分析整份文件（內容改變才重新分析）
	$effect(() => {
		if (isOpen && documentText.trim() && documentText !== analyzedText) {
			analyzedText = documentText;
			analyze(documentText);
		}
	});

	async function analyze(text: string) {
		loading = true;
		result = null;

		try {
			const response = await metadataWithAI(text);

			if (response.success && response.result) {
				result = response.result;
			} else {
				toastError(response.error || 'AI 文件分析失敗');
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
		result = null;
		analyzedText = null;
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
				<ScanText size={20} class="text-cta-500" />
				文件分析
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
			{#if loading}
				<div class="flex items-center justify-center py-8">
					<div
						class="border-cta-200 border-t-cta-500 h-8 w-8 animate-spin rounded-full border-3"
					></div>
					<span class="text-primary-600 ml-3">AI 分析中...</span>
				</div>
			{:else if result}
				<!-- 摘要 -->
				<div>
					<span class="text-primary-700 mb-2 block text-sm font-medium">摘要</span>
					<div
						class="border-cta-200 bg-cta-50 text-primary-800 rounded-lg border p-4 text-sm whitespace-pre-wrap"
					>
						{result.summary}
					</div>
				</div>

				<!-- 標籤 -->
				<div>
					<span class="text-primary-700 mb-2 flex items-center gap-1.5 text-sm font-medium">
						<Tag size={15} />
						標籤
					</span>
					<div class="flex flex-wrap gap-2">
						{#each result.tags as tag (tag)}
							<span
								class="bg-primary-100 text-primary-700 rounded-full px-3 py-1 text-xs font-medium"
							>
								{tag}
							</span>
						{/each}
					</div>
				</div>

				<!-- 語言 + 閱讀時間 -->
				<div class="flex gap-4">
					<div class="flex-1">
						<span class="text-primary-700 mb-1 flex items-center gap-1.5 text-sm font-medium">
							<Languages size={15} />
							語言
						</span>
						<div class="text-primary-800 text-sm">{result.language}</div>
					</div>
					<div class="flex-1">
						<span class="text-primary-700 mb-1 flex items-center gap-1.5 text-sm font-medium">
							<Clock size={15} />
							預估閱讀時間
						</span>
						<div class="text-primary-800 text-sm">{result.reading_time} 分鐘</div>
					</div>
				</div>
			{/if}
		</div>
	</div>
{/if}
