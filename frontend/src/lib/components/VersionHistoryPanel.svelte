<script lang="ts">
	import { browser } from '$app/environment';
	import {
		getVersions,
		getVersionDetail,
		restoreVersion,
		type DocumentVersion
	} from '$lib/api/versions';
	import { toastSuccess, toastError } from '$lib/toast';
	import { X, RotateCcw, Clock, User } from '@lucide/svelte';
	import ConfirmDialog from './ConfirmDialog.svelte';

	interface Props {
		documentId: string;
		isOpen: boolean;
		onRestore?: () => void;
	}

	let { documentId, isOpen = $bindable(false), onRestore = () => {} }: Props = $props();

	let versions = $state<DocumentVersion[]>([]);
	let loading = $state(false);
	let loadingMore = $state(false);
	let selectedVersion = $state<DocumentVersion | null>(null);
	let previewContent = $state<Record<string, unknown> | null>(null);
	let loadingPreview = $state(false);
	let previewContainer: HTMLElement | undefined;
	let previewQuill: import('quill').default | null = null;
	let restoring = $state(false);
	let currentPage = $state(1);
	let totalPages = $state(1);
	let hasMore = $derived(currentPage < totalPages);

	// 載入版本列表（第一頁）
	async function loadVersions() {
		if (!browser) return;

		loading = true;
		currentPage = 1;
		try {
			const result = await getVersions(documentId, 1);
			versions = result.items;
			totalPages = result.total_pages;
			currentPage = result.page;
		} catch (error) {
			toastError('載入版本失敗');
			console.error('Failed to load versions:', error);
		} finally {
			loading = false;
		}
	}

	// 載入更多版本
	async function loadMore() {
		if (!browser || loadingMore || !hasMore) return;

		loadingMore = true;
		try {
			const result = await getVersions(documentId, currentPage + 1);
			versions = [...versions, ...result.items];
			currentPage = result.page;
			totalPages = result.total_pages;
		} catch (error) {
			toastError('載入更多版本失敗');
			console.error('Failed to load more versions:', error);
		} finally {
			loadingMore = false;
		}
	}

	// 初始化或更新 readOnly Quill 預覽實例
	async function renderPreview(content: Record<string, unknown>) {
		if (!previewContainer) return;
		if (!previewQuill) {
			const { default: Quill } = await import('quill');
			previewQuill = new Quill(previewContainer, {
				theme: 'snow',
				readOnly: true,
				modules: { toolbar: false }
			});
		}
		const ops = (content as { ops?: unknown[] }).ops;
		if (Array.isArray(ops)) {
			previewQuill.setContents(ops, 'silent');
		}
	}

	// 預覽版本
	async function previewVersion(version: DocumentVersion) {
		if (selectedVersion?.id === version.id) return;
		selectedVersion = version;
		loadingPreview = true;
		try {
			const detail = await getVersionDetail(documentId, version.id);
			previewContent = detail.content;
			await renderPreview(detail.content);
		} catch (error) {
			toastError('載入版本內容失敗');
			console.error('Failed to load version detail:', error);
		} finally {
			loadingPreview = false;
		}
	}

	// 還原版本
	let showRestoreConfirm = $state(false);

	function handleRestore() {
		if (!selectedVersion || restoring) return;
		showRestoreConfirm = true;
	}

	async function confirmRestore() {
		if (!selectedVersion || restoring) return;

		restoring = true;
		try {
			const result = await restoreVersion(documentId, selectedVersion.id);
			toastSuccess(result.message);
			isOpen = false;
			onRestore();
		} catch (error) {
			toastError('還原失敗');
			console.error('Failed to restore version:', error);
		} finally {
			restoring = false;
		}
	}

	// 格式化時間
	function formatTime(dateStr: string): string {
		const date = new Date(dateStr);
		return date.toLocaleString('zh-TW', {
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	// 關閉面板
	function closePanel() {
		isOpen = false;
		previewQuill = null;
		selectedVersion = null;
		previewContent = null;
	}

	// 監聽 isOpen 變化載入版本
	$effect(() => {
		if (isOpen && browser) {
			loadVersions();
		}
	});
</script>

{#if isOpen}
	<!-- 背景遮罩 -->
	<button
		type="button"
		class="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
		onclick={closePanel}
		onkeydown={(e) => e.key === 'Escape' && closePanel()}
		aria-label="關閉版本歷史"
	></button>

	<!-- 側邊面板 -->
	<div
		class="border-primary-200 fixed top-0 right-0 z-50 flex h-full w-full flex-col border-l bg-white shadow-2xl sm:w-96"
	>
		<!-- 標題 -->
		<div class="border-primary-200 flex items-center justify-between border-b p-4">
			<div class="flex items-center gap-2">
				<Clock size={20} class="text-primary-500" />
				<h2 class="text-primary-900 text-lg font-semibold">版本歷史</h2>
			</div>
			<button
				type="button"
				class="text-primary-400 hover:bg-primary-100 hover:text-primary-600 cursor-pointer rounded-lg p-1.5 transition-colors"
				onclick={closePanel}
				aria-label="關閉"
			>
				<X size={20} />
			</button>
		</div>

		<!-- 版本列表 -->
		<div class="flex-1 overflow-y-auto">
			{#if loading}
				<div class="flex items-center justify-center py-12">
					<div
						class="border-primary-200 border-t-primary-600 h-6 w-6 animate-spin rounded-full border-2"
					></div>
					<span class="text-primary-500 ml-2">載入中...</span>
				</div>
			{:else if versions.length === 0}
				<div class="py-12 text-center">
					<Clock size={40} class="text-primary-300 mx-auto mb-3" />
					<p class="text-primary-500">尚無版本記錄</p>
				</div>
			{:else}
				<div class="divide-primary-100 divide-y">
					{#each versions as version (version.id)}
						<button
							type="button"
							class="hover:bg-primary-50 w-full cursor-pointer p-4 text-left transition-colors
								   {selectedVersion?.id === version.id
								? 'border-primary-500 bg-primary-50 border-l-2'
								: 'border-l-2 border-transparent'}"
							onclick={() => previewVersion(version)}
						>
							<div class="flex items-center justify-between">
								<span class="text-primary-800 font-medium">版本 {version.version_number}</span>
								<span class="text-primary-500 text-sm">{formatTime(version.created_at)}</span>
							</div>
							{#if version.created_by_username}
								<div class="text-primary-500 mt-1.5 flex items-center gap-1 text-sm">
									<User size={14} />
									<span>{version.created_by_username}</span>
								</div>
							{/if}
						</button>
					{/each}
				</div>
				{#if hasMore}
					<div class="p-4 text-center">
						<button
							type="button"
							class="text-primary-600 hover:bg-primary-100 cursor-pointer rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50"
							onclick={loadMore}
							disabled={loadingMore}
						>
							{#if loadingMore}
								<span class="inline-flex items-center gap-2">
									<span
										class="border-primary-300 border-t-primary-600 h-4 w-4 animate-spin rounded-full border-2"
									></span>
									載入中...
								</span>
							{:else}
								載入更多版本
							{/if}
						</button>
					</div>
				{/if}
			{/if}
		</div>

		<!-- 版本內容預覽 -->
		{#if selectedVersion}
			<div class="border-primary-200 border-t">
				<div class="border-primary-200 bg-primary-50 flex items-center gap-2 border-b px-4 py-2">
					<span class="text-primary-700 text-sm font-medium">
						版本 {selectedVersion.version_number} 預覽
					</span>
				</div>
				<div class="preview-quill max-h-[27rem] overflow-y-auto">
					{#if loadingPreview}
						<div class="flex items-center justify-center py-4">
							<div
								class="border-primary-200 border-t-primary-600 h-4 w-4 animate-spin rounded-full border-2"
							></div>
							<span class="text-primary-500 ml-2 text-sm">載入中...</span>
						</div>
					{/if}
					<div bind:this={previewContainer} class:hidden={loadingPreview || !previewContent}></div>
					{#if !loadingPreview && !previewContent}
						<p class="text-primary-400 p-4 text-sm">無法載入內容</p>
					{/if}
				</div>
			</div>
		{/if}

		<!-- 還原按鈕 -->
		{#if selectedVersion}
			<div class="border-primary-200 border-t p-4">
				<button
					type="button"
					class="bg-primary-600 hover:bg-primary-700 flex w-full cursor-pointer items-center justify-center gap-2 rounded-lg px-4 py-2.5 font-medium text-white
							 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
					onclick={handleRestore}
					disabled={restoring}
				>
					{#if restoring}
						<span
							class="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"
						></span>
						<span>還原中...</span>
					{:else}
						<RotateCcw size={18} />
						<span>還原到版本 {selectedVersion.version_number}</span>
					{/if}
				</button>
			</div>
		{/if}
	</div>
{/if}

<ConfirmDialog
	bind:isOpen={showRestoreConfirm}
	title="還原版本"
	message={selectedVersion
		? `確定要還原到版本 ${selectedVersion.version_number}？這將覆蓋目前的內容。`
		: ''}
	confirmText="還原"
	variant="warning"
	onConfirm={confirmRestore}
/>

<style>
	.preview-quill :global(.ql-toolbar) {
		display: none;
	}
	.preview-quill :global(.ql-container) {
		border: none;
		font-size: 14px;
	}
	.preview-quill :global(.ql-editor) {
		padding: 0.75rem 1rem;
		min-height: auto;
		line-height: 1.5;
	}
</style>
