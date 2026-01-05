<script lang="ts">
	import { browser } from '$app/environment';
	import {
		getVersions,
		getVersionDetail,
		restoreVersion,
		type DocumentVersion
	} from '$lib/api/versions';
	import { toast } from '@zerodevx/svelte-toast';

	interface Props {
		documentId: string;
		isOpen: boolean;
		onRestore?: () => void;
	}

	let { documentId, isOpen = $bindable(false), onRestore = () => {} }: Props = $props();

	let versions = $state<DocumentVersion[]>([]);
	let loading = $state(false);
	let selectedVersion = $state<DocumentVersion | null>(null);
	let previewContent = $state<Record<string, unknown> | null>(null);
	let restoring = $state(false);

	// 載入版本列表
	async function loadVersions() {
		if (!browser) return;

		loading = true;
		try {
			versions = await getVersions(documentId);
		} catch (error) {
			toast.push('載入版本失敗', { theme: { '--toastBackground': '#ef4444' } });
			console.error('Failed to load versions:', error);
		} finally {
			loading = false;
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
	async function handleRestore() {
		if (!selectedVersion || restoring) return;

		const confirmed = confirm(
			`確定要還原到版本 ${selectedVersion.version_number}？\n這將覆蓋目前的內容。`
		);
		if (!confirmed) return;

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
		class="fixed inset-0 z-40 bg-black/50"
		onclick={closePanel}
		onkeydown={(e) => e.key === 'Escape' && closePanel()}
		aria-label="關閉版本歷史"
	></button>

	<!-- 側邊面板 -->
	<div class="fixed top-0 right-0 z-50 flex h-full w-96 flex-col bg-white shadow-xl">
		<!-- 標題 -->
		<div class="flex items-center justify-between border-b p-4">
			<h2 class="text-lg font-semibold">版本歷史</h2>
			<button
				type="button"
				class="text-gray-500 hover:text-gray-700"
				onclick={closePanel}
				aria-label="關閉"
			>
				<svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M6 18L18 6M6 6l12 12"
					/>
				</svg>
			</button>
		</div>

		<!-- 版本列表 -->
		<div class="flex-1 overflow-y-auto">
			{#if loading}
				<div class="p-4 text-center text-gray-500">載入中...</div>
			{:else if versions.length === 0}
				<div class="p-4 text-center text-gray-500">尚無版本記錄</div>
			{:else}
				<div class="divide-y">
					{#each versions as version (version.id)}
						<button
							type="button"
							class="w-full p-4 text-left transition-colors hover:bg-gray-50
								   {selectedVersion?.id === version.id ? 'bg-blue-50' : ''}"
							onclick={() => previewVersion(version)}
						>
							<div class="flex items-center justify-between">
								<span class="font-medium">版本 {version.version_number}</span>
								<span class="text-sm text-gray-500">{formatTime(version.created_at)}</span>
							</div>
							{#if version.created_by_username}
								<div class="mt-1 text-sm text-gray-500">
									由 {version.created_by_username} 編輯
								</div>
							{/if}
						</button>
					{/each}
				</div>
			{/if}
		</div>

		<!-- 還原按鈕 -->
		{#if selectedVersion}
			<div class="border-t p-4">
				<button
					type="button"
					class="w-full rounded-lg bg-blue-600 px-4 py-2 text-white transition-colors
							 hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
					onclick={handleRestore}
					disabled={restoring}
				>
					{#if restoring}
						還原中...
					{:else}
						還原到版本 {selectedVersion.version_number}
					{/if}
				</button>
			</div>
		{/if}
	</div>
{/if}
