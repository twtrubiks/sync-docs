<script lang="ts">
	import { browser } from '$app/environment';
	import {
		getVersions,
		getVersionDetail,
		restoreVersion,
		type DocumentVersion
	} from '$lib/api/versions';
	import { toast } from '@zerodevx/svelte-toast';
	import { X, RotateCcw, Clock, User } from 'lucide-svelte';
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
			toast.push('載入版本失敗', { theme: { '--toastBackground': '#ef4444' } });
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
			toast.push('載入更多版本失敗', { theme: { '--toastBackground': '#ef4444' } });
			console.error('Failed to load more versions:', error);
		} finally {
			loadingMore = false;
		}
	}

	// 預覽版本
	async function previewVersion(version: DocumentVersion) {
		selectedVersion = version;
		try {
			const detail = await getVersionDetail(documentId, version.id);
			previewContent = detail.content;
		} catch (error) {
			toast.push('載入版本內容失敗', { theme: { '--toastBackground': '#ef4444' } });
			console.error('Failed to load version detail:', error);
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
			toast.push(result.message, { theme: { '--toastBackground': '#22c55e' } });
			isOpen = false;
			onRestore();
		} catch (error) {
			toast.push('還原失敗', { theme: { '--toastBackground': '#ef4444' } });
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
		class="fixed top-0 right-0 z-50 flex h-full w-full flex-col border-l border-primary-200 bg-white shadow-2xl sm:w-96"
	>
		<!-- 標題 -->
		<div class="flex items-center justify-between border-b border-primary-200 p-4">
			<div class="flex items-center gap-2">
				<Clock size={20} class="text-primary-500" />
				<h2 class="text-lg font-semibold text-primary-900">版本歷史</h2>
			</div>
			<button
				type="button"
				class="cursor-pointer rounded-lg p-1.5 text-primary-400 transition-colors hover:bg-primary-100 hover:text-primary-600"
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
						class="h-6 w-6 animate-spin rounded-full border-2 border-primary-200 border-t-primary-600"
					></div>
					<span class="ml-2 text-primary-500">載入中...</span>
				</div>
			{:else if versions.length === 0}
				<div class="py-12 text-center">
					<Clock size={40} class="mx-auto mb-3 text-primary-300" />
					<p class="text-primary-500">尚無版本記錄</p>
				</div>
			{:else}
				<div class="divide-y divide-primary-100">
					{#each versions as version (version.id)}
						<button
							type="button"
							class="w-full cursor-pointer p-4 text-left transition-colors hover:bg-primary-50
								   {selectedVersion?.id === version.id
								? 'border-l-2 border-primary-500 bg-primary-50'
								: 'border-l-2 border-transparent'}"
							onclick={() => previewVersion(version)}
						>
							<div class="flex items-center justify-between">
								<span class="font-medium text-primary-800">版本 {version.version_number}</span>
								<span class="text-sm text-primary-500">{formatTime(version.created_at)}</span>
							</div>
							{#if version.created_by_username}
								<div class="mt-1.5 flex items-center gap-1 text-sm text-primary-500">
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
							class="cursor-pointer rounded-lg px-4 py-2 text-sm font-medium text-primary-600 transition-colors hover:bg-primary-100 disabled:cursor-not-allowed disabled:opacity-50"
							onclick={loadMore}
							disabled={loadingMore}
						>
							{#if loadingMore}
								<span class="inline-flex items-center gap-2">
									<span class="h-4 w-4 animate-spin rounded-full border-2 border-primary-300 border-t-primary-600"></span>
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

		<!-- 還原按鈕 -->
		{#if selectedVersion}
			<div class="border-t border-primary-200 p-4">
				<button
					type="button"
					class="flex w-full cursor-pointer items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 py-2.5 font-medium text-white transition-colors
							 hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50"
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
	message={selectedVersion ? `確定要還原到版本 ${selectedVersion.version_number}？這將覆蓋目前的內容。` : ''}
	confirmText="還原"
	variant="warning"
	onConfirm={confirmRestore}
/>
