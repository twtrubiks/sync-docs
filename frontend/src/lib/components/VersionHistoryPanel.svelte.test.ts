import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import VersionHistoryPanel from './VersionHistoryPanel.svelte';

// Mock API 模組
vi.mock('$lib/api/versions', () => ({
	getVersions: vi.fn(),
	getVersionDetail: vi.fn(),
	restoreVersion: vi.fn()
}));

// Mock toast
vi.mock('@zerodevx/svelte-toast', () => ({
	toast: { push: vi.fn() }
}));

// Mock $app/environment
vi.mock('$app/environment', () => ({
	browser: true
}));

import { getVersions, getVersionDetail, restoreVersion } from '$lib/api/versions';

const mockVersions = [
	{
		id: 'version-1',
		version_number: 2,
		created_at: '2024-01-15T10:30:00Z',
		created_by_username: 'testuser'
	},
	{
		id: 'version-2',
		version_number: 1,
		created_at: '2024-01-15T09:00:00Z',
		created_by_username: 'testuser'
	}
];

describe('VersionHistoryPanel', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		vi.mocked(getVersions).mockResolvedValue(mockVersions);
	});

	it('should load versions when opened', async () => {
		render(VersionHistoryPanel, {
			props: {
				documentId: 'doc-123',
				isOpen: true
			}
		});

		await waitFor(() => {
			expect(getVersions).toHaveBeenCalledWith('doc-123');
		});

		expect(screen.getByText('版本 2')).toBeInTheDocument();
		expect(screen.getByText('版本 1')).toBeInTheDocument();
	});

	it('should not load versions when closed', () => {
		render(VersionHistoryPanel, {
			props: {
				documentId: 'doc-123',
				isOpen: false
			}
		});

		expect(getVersions).not.toHaveBeenCalled();
	});

	it('should show empty state message', async () => {
		vi.mocked(getVersions).mockResolvedValue([]);

		render(VersionHistoryPanel, {
			props: {
				documentId: 'doc-123',
				isOpen: true
			}
		});

		await waitFor(() => {
			expect(screen.getByText('尚無版本記錄')).toBeInTheDocument();
		});
	});

	it('should load version detail when clicked', async () => {
		vi.mocked(getVersionDetail).mockResolvedValue({
			...mockVersions[0],
			content: { ops: [{ insert: 'test' }] }
		});

		render(VersionHistoryPanel, {
			props: {
				documentId: 'doc-123',
				isOpen: true
			}
		});

		await waitFor(() => {
			expect(screen.getByText('版本 2')).toBeInTheDocument();
		});

		await fireEvent.click(screen.getByText('版本 2'));

		expect(getVersionDetail).toHaveBeenCalledWith('doc-123', 'version-1');
	});

	it('should show restore button when version is selected', async () => {
		vi.mocked(getVersionDetail).mockResolvedValue({
			...mockVersions[0],
			content: { ops: [{ insert: 'test' }] }
		});

		render(VersionHistoryPanel, {
			props: {
				documentId: 'doc-123',
				isOpen: true
			}
		});

		await waitFor(() => {
			expect(screen.getByText('版本 2')).toBeInTheDocument();
		});

		await fireEvent.click(screen.getByText('版本 2'));

		await waitFor(() => {
			expect(screen.getByText('還原到版本 2')).toBeInTheDocument();
		});
	});

	it('should call restore API and callback when restored', async () => {
		const onRestore = vi.fn();
		vi.mocked(getVersionDetail).mockResolvedValue({
			...mockVersions[0],
			content: { ops: [{ insert: 'test' }] }
		});
		vi.mocked(restoreVersion).mockResolvedValue({
			success: true,
			message: '已還原到版本 2',
			new_version_number: 3
		});

		// Mock confirm
		vi.spyOn(window, 'confirm').mockReturnValue(true);

		render(VersionHistoryPanel, {
			props: {
				documentId: 'doc-123',
				isOpen: true,
				onRestore
			}
		});

		await waitFor(() => {
			expect(screen.getByText('版本 2')).toBeInTheDocument();
		});

		await fireEvent.click(screen.getByText('版本 2'));

		await waitFor(() => {
			expect(screen.getByText('還原到版本 2')).toBeInTheDocument();
		});

		await fireEvent.click(screen.getByText('還原到版本 2'));

		await waitFor(() => {
			expect(restoreVersion).toHaveBeenCalledWith('doc-123', 'version-1');
			expect(onRestore).toHaveBeenCalled();
		});
	});

	it('should display created_by_username', async () => {
		render(VersionHistoryPanel, {
			props: {
				documentId: 'doc-123',
				isOpen: true
			}
		});

		await waitFor(() => {
			// 因為有多個版本都是同一用戶創建，所以用 getAllByText
			const elements = screen.getAllByText('由 testuser 編輯');
			expect(elements.length).toBe(2);
		});
	});

	it('should show panel title', async () => {
		render(VersionHistoryPanel, {
			props: {
				documentId: 'doc-123',
				isOpen: true
			}
		});

		expect(screen.getByText('版本歷史')).toBeInTheDocument();
	});
});
