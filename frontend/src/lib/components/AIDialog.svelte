<script lang="ts">
	import { processWithAI, proofreadWithAI, type ProofreadResult } from '$lib/ai';
	import { toastError, toastWarning } from '$lib/toast';
	import { X, Sparkles, FileText, WandSparkles, Check, SpellCheck } from '@lucide/svelte';

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
	let currentAction = $state<'summarize' | 'polish' | 'proofread' | null>(null);

	// 校對狀態：結構化結果 + 逐項套用後的工作文字
	let proofreadResult = $state<ProofreadResult | null>(null);
	let workingText = $state('');
	let appliedIndexes = $state<number[]>([]);

	async function handleAction(action: 'summarize' | 'polish') {
		if (!selectedText.trim()) {
			toastWarning('Please select text first');
			return;
		}

		loading = true;
		currentAction = action;
		result = '';
		proofreadResult = null;

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

	async function handleProofread() {
		if (!selectedText.trim()) {
			toastWarning('Please select text first');
			return;
		}

		loading = true;
		currentAction = 'proofread';
		result = '';
		proofreadResult = null;
		appliedIndexes = [];

		try {
			const response = await proofreadWithAI(selectedText);

			if (response.success && response.result) {
				proofreadResult = response.result;
				workingText = selectedText;
			} else {
				toastError(response.error || 'AI proofreading failed');
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

	// 逐項套用：在工作文字中以字串比對取代第一個符合的 original
	function applyIssue(index: number) {
		if (!proofreadResult || appliedIndexes.includes(index)) return;

		const issue = proofreadResult.issues[index];
		if (!workingText.includes(issue.original)) {
			toastWarning('找不到原文片段，可能已被其他建議修改');
			return;
		}

		workingText = workingText.replace(issue.original, issue.suggestion);
		appliedIndexes = [...appliedIndexes, index];
	}

	function handleApply() {
		if (result) {
			onApply(result);
			close();
		}
	}

	function handleApplyProofread() {
		if (appliedIndexes.length === 0) return;
		onApply(workingText);
		close();
	}

	function close() {
		isOpen = false;
		result = '';
		currentAction = null;
		proofreadResult = null;
		workingText = '';
		appliedIndexes = [];
	}

	const actionLabels = {
		summarize: '摘要結果',
		polish: '潤稿結果',
		proofread: '校對結果'
	};

	// severity 對應的色彩樣式
	const severityStyles: Record<string, string> = {
		info: 'bg-blue-100 text-blue-700',
		warning: 'bg-amber-100 text-amber-700',
		error: 'bg-red-100 text-red-700'
	};
	const severityLabels: Record<string, string> = {
		info: '提示',
		warning: '建議',
		error: '錯誤'
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
				<button
					class="flex flex-1 cursor-pointer items-center justify-center gap-2 rounded-lg border-2 px-4 py-3 font-medium transition-all duration-150
                 {currentAction === 'proofread'
						? 'border-cta-500 bg-cta-50 text-cta-700'
						: 'border-primary-200 text-primary-600 hover:border-cta-300 hover:bg-cta-50'}
                 disabled:cursor-not-allowed disabled:opacity-50"
					onclick={handleProofread}
					disabled={loading || !selectedText.trim()}
				>
					<SpellCheck size={18} />
					校對
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
			{:else if currentAction === 'proofread' && proofreadResult}
				<div>
					<div class="mb-2 flex items-center justify-between">
						<span class="text-primary-700 text-sm font-medium">
							{actionLabels.proofread}
						</span>
						<span class="text-primary-600 text-sm">
							整體分數 <span class="text-cta-700 font-semibold"
								>{proofreadResult.overall_score}</span
							>/100
						</span>
					</div>

					{#if proofreadResult.issues.length === 0}
						<div
							class="border-cta-200 bg-cta-50 text-primary-700 rounded-lg border p-4 text-center text-sm"
						>
							沒有發現明顯問題 🎉
						</div>
					{:else}
						<div class="max-h-64 space-y-3 overflow-y-auto">
							{#each proofreadResult.issues as issue, index (index)}
								<div class="border-primary-200 rounded-lg border p-3 text-sm">
									<div class="mb-2 flex items-center justify-between gap-2">
										<span
											class="rounded px-2 py-0.5 text-xs font-medium {severityStyles[
												issue.severity
											]}"
										>
											{severityLabels[issue.severity] ?? issue.severity}
										</span>
										<button
											class="bg-cta-500 hover:bg-cta-600 cursor-pointer rounded px-3 py-1 text-xs font-medium text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50"
											onclick={() => applyIssue(index)}
											disabled={appliedIndexes.includes(index)}
										>
											{appliedIndexes.includes(index) ? '已套用' : '套用'}
										</button>
									</div>
									<div class="text-primary-500 mb-1 line-through">{issue.original}</div>
									<div class="text-primary-800 mb-1 font-medium">{issue.suggestion}</div>
									<div class="text-primary-500 text-xs">{issue.reason}</div>
								</div>
							{/each}
						</div>
					{/if}
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
		{#if currentAction === 'proofread' && proofreadResult && proofreadResult.issues.length > 0}
			<div class="border-primary-200 flex justify-end gap-3 border-t p-4">
				<button
					class="border-primary-300 text-primary-700 hover:bg-primary-50 cursor-pointer rounded-lg border px-4 py-2 font-medium transition-colors"
					onclick={close}
				>
					取消
				</button>
				<button
					class="bg-cta-500 hover:bg-cta-600 flex cursor-pointer items-center gap-2 rounded-lg px-4 py-2 font-medium text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50"
					onclick={handleApplyProofread}
					disabled={appliedIndexes.length === 0}
				>
					<Check size={18} />
					套用變更到文件
				</button>
			</div>
		{:else if result}
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
