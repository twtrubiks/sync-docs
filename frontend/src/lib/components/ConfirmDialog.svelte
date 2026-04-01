<script lang="ts">
	import { TriangleAlert, X } from '@lucide/svelte';

	let {
		isOpen = $bindable(false),
		title = '確認操作',
		message = '確定要執行此操作嗎？',
		confirmText = '確認',
		cancelText = '取消',
		variant = 'danger',
		onConfirm = () => {},
		onCancel = () => {}
	}: {
		isOpen: boolean;
		title?: string;
		message?: string;
		confirmText?: string;
		cancelText?: string;
		variant?: 'danger' | 'warning';
		onConfirm?: () => void;
		onCancel?: () => void;
	} = $props();

	function handleConfirm() {
		isOpen = false;
		onConfirm();
	}

	function handleCancel() {
		isOpen = false;
		onCancel();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && isOpen) {
			handleCancel();
		}
	}

	const variantStyles = {
		danger: {
			icon: 'text-red-500',
			confirmBtn: 'bg-red-600 hover:bg-red-700 text-white',
			iconBg: 'bg-red-100'
		},
		warning: {
			icon: 'text-amber-500',
			confirmBtn: 'bg-amber-500 hover:bg-amber-600 text-white',
			iconBg: 'bg-amber-100'
		}
	};

	let styles = $derived(variantStyles[variant]);
</script>

<svelte:window onkeydown={handleKeydown} />

{#if isOpen}
	<!-- Background overlay -->
	<button
		type="button"
		class="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm"
		onclick={handleCancel}
		aria-label="關閉對話框"
		data-testid="confirm-dialog-overlay"
	></button>

	<!-- Dialog -->
	<div
		class="border-primary-200 fixed top-1/2 left-1/2 z-50 w-[420px]
              max-w-[90vw] -translate-x-1/2 -translate-y-1/2 rounded-xl border bg-white shadow-2xl"
		role="alertdialog"
		aria-modal="true"
		aria-labelledby="confirm-dialog-title"
		aria-describedby="confirm-dialog-message"
	>
		<!-- Header -->
		<div class="border-primary-100 flex items-center justify-between border-b p-4">
			<h2
				id="confirm-dialog-title"
				class="text-primary-900 flex items-center gap-2 text-lg font-semibold"
			>
				<span class="flex h-8 w-8 items-center justify-center rounded-full {styles.iconBg}">
					<TriangleAlert size={18} class={styles.icon} />
				</span>
				{title}
			</h2>
			<button
				class="text-primary-400 hover:bg-primary-100 hover:text-primary-600 cursor-pointer rounded-lg p-1.5 transition-colors"
				onclick={handleCancel}
				aria-label="關閉"
			>
				<X size={20} />
			</button>
		</div>

		<!-- Content -->
		<div class="p-5">
			<p id="confirm-dialog-message" class="text-primary-600 text-sm leading-relaxed">
				{message}
			</p>
		</div>

		<!-- Footer -->
		<div class="border-primary-100 flex justify-end gap-3 border-t px-5 py-4">
			<button
				class="border-primary-300 text-primary-700 hover:bg-primary-50 cursor-pointer rounded-lg border px-4 py-2 text-sm font-medium transition-colors"
				onclick={handleCancel}
			>
				{cancelText}
			</button>
			<button
				class="cursor-pointer rounded-lg px-4 py-2 text-sm font-medium transition-colors {styles.confirmBtn}"
				onclick={handleConfirm}
				data-testid="confirm-dialog-confirm-btn"
			>
				{confirmText}
			</button>
		</div>
	</div>
{/if}
