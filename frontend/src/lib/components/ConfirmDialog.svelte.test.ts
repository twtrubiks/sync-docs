import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import ConfirmDialog from './ConfirmDialog.svelte';

// Mock $app/environment
vi.mock('$app/environment', () => ({
	browser: true
}));

describe('ConfirmDialog', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('isOpen 為 false 時不渲染', () => {
		render(ConfirmDialog, {
			props: { isOpen: false }
		});
		expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
	});

	it('isOpen 為 true 時渲染對話框', () => {
		render(ConfirmDialog, {
			props: {
				isOpen: true,
				title: '刪除文件',
				message: '確定要刪除嗎？'
			}
		});
		expect(screen.getByRole('alertdialog')).toBeInTheDocument();
		expect(screen.getByText('刪除文件')).toBeInTheDocument();
		expect(screen.getByText('確定要刪除嗎？')).toBeInTheDocument();
	});

	it('顯示自訂的確認和取消按鈕文字', () => {
		render(ConfirmDialog, {
			props: {
				isOpen: true,
				confirmText: '刪除',
				cancelText: '返回'
			}
		});
		expect(screen.getByText('刪除')).toBeInTheDocument();
		expect(screen.getByText('返回')).toBeInTheDocument();
	});

	it('顯示預設的確認和取消按鈕文字', () => {
		render(ConfirmDialog, {
			props: { isOpen: true }
		});
		expect(screen.getByText('確認')).toBeInTheDocument();
		expect(screen.getByText('取消')).toBeInTheDocument();
	});

	it('點擊確認按鈕觸發 onConfirm 回呼', async () => {
		const onConfirm = vi.fn();
		render(ConfirmDialog, {
			props: {
				isOpen: true,
				confirmText: '刪除',
				onConfirm
			}
		});

		await fireEvent.click(screen.getByTestId('confirm-dialog-confirm-btn'));
		expect(onConfirm).toHaveBeenCalledOnce();
	});

	it('點擊取消按鈕觸發 onCancel 回呼', async () => {
		const onCancel = vi.fn();
		render(ConfirmDialog, {
			props: {
				isOpen: true,
				onCancel
			}
		});

		await fireEvent.click(screen.getByText('取消'));
		expect(onCancel).toHaveBeenCalledOnce();
	});

	it('點擊背景遮罩觸發 onCancel 回呼', async () => {
		const onCancel = vi.fn();
		render(ConfirmDialog, {
			props: {
				isOpen: true,
				onCancel
			}
		});

		await fireEvent.click(screen.getByTestId('confirm-dialog-overlay'));
		expect(onCancel).toHaveBeenCalledOnce();
	});

	it('按 Escape 鍵觸發 onCancel 回呼', async () => {
		const onCancel = vi.fn();
		render(ConfirmDialog, {
			props: {
				isOpen: true,
				onCancel
			}
		});

		await fireEvent.keyDown(window, { key: 'Escape' });
		expect(onCancel).toHaveBeenCalledOnce();
	});

	it('danger variant 渲染紅色確認按鈕', () => {
		render(ConfirmDialog, {
			props: {
				isOpen: true,
				variant: 'danger'
			}
		});

		const confirmBtn = screen.getByTestId('confirm-dialog-confirm-btn');
		expect(confirmBtn.className).toContain('bg-red-600');
	});

	it('warning variant 渲染黃色確認按鈕', () => {
		render(ConfirmDialog, {
			props: {
				isOpen: true,
				variant: 'warning'
			}
		});

		const confirmBtn = screen.getByTestId('confirm-dialog-confirm-btn');
		expect(confirmBtn.className).toContain('bg-amber-500');
	});

	it('點擊關閉按鈕（X）觸發 onCancel 回呼', async () => {
		const onCancel = vi.fn();
		render(ConfirmDialog, {
			props: {
				isOpen: true,
				onCancel
			}
		});

		const closeBtn = screen.getByLabelText('關閉');
		await fireEvent.click(closeBtn);
		expect(onCancel).toHaveBeenCalledOnce();
	});
});
