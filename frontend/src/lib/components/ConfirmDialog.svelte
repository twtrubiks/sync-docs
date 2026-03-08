<script lang="ts">
	import { AlertTriangle, X } from 'lucide-svelte';

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
		class="fixed top-1/2 left-1/2 z-50 w-[420px] max-w-[90vw]
              -translate-x-1/2 -translate-y-1/2 rounded-xl border border-primary-200 bg-white shadow-2xl"
		role="alertdialog"
		aria-modal="true"
		aria-labelledby="confirm-dialog-title"
		aria-describedby="confirm-dialog-message"
	>
		<!-- Header -->
		<div class="flex items-center justify-between border-b border-primary-100 p-4">
			<h2
				id="confirm-dialog-title"
				class="flex items-center gap-2 text-lg font-semibold text-primary-900"
			>
				<span class="flex h-8 w-8 items-center justify-center rounded-full {styles.iconBg}">
					<AlertTriangle size={18} class={styles.icon} />
				</span>
				{title}
			</h2>
			<button
				class="cursor-pointer rounded-lg p-1.5 text-primary-400 transition-colors hover:bg-primary-100 hover:text-primary-600"
				onclick={handleCancel}
				aria-label="關閉"
			>
				<X size={20} />
			</button>
		</div>

		<!-- Content -->
		<div class="p-5">
			<p id="confirm-dialog-message" class="text-sm leading-relaxed text-primary-600">
				{message}
			</p>
		</div>

		<!-- Footer -->
		<div class="flex justify-end gap-3 border-t border-primary-100 px-5 py-4">
			<button
				class="cursor-pointer rounded-lg border border-primary-300 px-4 py-2 text-sm font-medium text-primary-700 transition-colors hover:bg-primary-50"
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
