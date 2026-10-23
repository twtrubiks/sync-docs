import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, waitFor } from '@testing-library/svelte';

vi.mock('$app/environment', () => ({ browser: true }));

// jsdom 無法執行真正的 Quill；以 mock 驗證元件與 Quill / quill-cursors 之間的橋接
const quill = vi.hoisted(() => {
	type Handler = (...args: unknown[]) => void;
	const cursors = {
		list: [] as { id: string }[],
		cursors: vi.fn(() => cursors.list),
		createCursor: vi.fn(),
		moveCursor: vi.fn(),
		removeCursor: vi.fn()
	};
	const instances: MockQuill[] = [];
	class MockQuill {
		static register = vi.fn();
		options: unknown;
		handlers: Record<string, Handler> = {};
		contents: { ops: unknown[] } = { ops: [] };
		getModule = vi.fn(() => cursors);
		setContents = vi.fn((ops: unknown[]) => {
			this.contents = { ops };
		});
		getContents = vi.fn(() => this.contents);
		on = vi.fn((event: string, handler: Handler) => {
			this.handlers[event] = handler;
		});
		off = vi.fn();
		enable = vi.fn();
		constructor(_container: HTMLElement, options: unknown) {
			this.options = options;
			instances.push(this);
		}
	}
	return { MockQuill, instances, cursors, CursorsModule: class {} };
});

vi.mock('quill', () => ({ default: quill.MockQuill }));
vi.mock('quill-cursors', () => ({ default: quill.CursorsModule }));

import QuillEditor from './QuillEditor.svelte';

async function renderEditor(props: Record<string, unknown> = {}) {
	const result = render(QuillEditor, { props });
	await waitFor(() => expect(quill.instances).toHaveLength(1));
	await waitFor(() => expect(quill.instances[0].on).toHaveBeenCalledTimes(2));
	return { ...result, editor: quill.instances[0] };
}

describe('QuillEditor', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		quill.instances.length = 0;
		quill.cursors.list = [];
	});

	it('creates a snow editor with the cursors module and toolbar', async () => {
		const { editor } = await renderEditor();

		expect(quill.MockQuill.register).toHaveBeenCalledWith('modules/cursors', quill.CursorsModule);
		expect(editor.options).toMatchObject({
			theme: 'snow',
			modules: {
				cursors: {
					hideDelayMs: 5000,
					hideSpeedMs: 300,
					selectionChangeSource: null,
					transformOnTextChange: true
				}
			}
		});
		expect((editor.options as { modules: { toolbar: unknown[] } }).modules.toolbar).toHaveLength(5);
		expect(editor.getModule).toHaveBeenCalledWith('cursors');
	});

	it('loads initial content silently, and skips empty content', async () => {
		const ops = [{ insert: 'Hello\n' }];
		const { editor } = await renderEditor({ value: { ops } });
		expect(editor.setContents).toHaveBeenCalledWith(ops, 'silent');

		document.body.innerHTML = '';
		quill.instances.length = 0;
		const { editor: empty } = await renderEditor({ value: { ops: [] } });
		expect(empty.setContents).not.toHaveBeenCalled();
	});

	it('forwards text changes with their source', async () => {
		const onTextChange = vi.fn();
		const { editor } = await renderEditor({ onTextChange });
		const delta = { ops: [{ insert: 'x' }] };

		editor.handlers['text-change'](delta, { ops: [] }, 'user');

		expect(onTextChange).toHaveBeenCalledWith({ delta, source: 'user' });
		expect(editor.getContents).toHaveBeenCalled();
	});

	it('forwards only user selections that have a range', async () => {
		const onSelectionChange = vi.fn();
		const { editor } = await renderEditor({ onSelectionChange });
		const range = { index: 3, length: 2 };

		editor.handlers['selection-change'](range, null, 'api');
		editor.handlers['selection-change'](null, null, 'user');
		expect(onSelectionChange).not.toHaveBeenCalled();

		editor.handlers['selection-change'](range, null, 'user');
		expect(onSelectionChange).toHaveBeenCalledWith(range);
	});

	it('creates a cursor once and then only moves it', async () => {
		const { component } = await renderEditor();
		const range = { index: 1, length: 0 };

		component.setCursor('u1', 'alice', '#ff0000', range);
		expect(quill.cursors.createCursor).toHaveBeenCalledWith('u1', 'alice', '#ff0000');
		expect(quill.cursors.moveCursor).toHaveBeenCalledWith('u1', range);

		quill.cursors.list = [{ id: 'u1' }];
		component.setCursor('u1', 'alice', '#ff0000', { index: 5, length: 1 });
		expect(quill.cursors.createCursor).toHaveBeenCalledTimes(1);
		expect(quill.cursors.moveCursor).toHaveBeenLastCalledWith('u1', { index: 5, length: 1 });

		component.removeCursor('u1');
		expect(quill.cursors.removeCursor).toHaveBeenCalledWith('u1');
	});

	it.each([
		[true, false],
		[false, true]
	])('disabled=%s enables the editor: %s', async (disabled, enabled) => {
		const { editor } = await renderEditor({ disabled });

		await waitFor(() => expect(editor.enable).toHaveBeenLastCalledWith(enabled));
	});

	it('does not re-apply content that the editor already has', async () => {
		const ops = [{ insert: 'Hello\n' }];
		const { editor } = await renderEditor({ value: { ops } });

		await waitFor(() => expect(editor.enable).toHaveBeenCalled());
		expect(editor.setContents).toHaveBeenCalledTimes(1);
	});

	it('removes its listeners on unmount', async () => {
		const { editor, unmount } = await renderEditor();
		const textHandler = editor.handlers['text-change'];
		const selectionHandler = editor.handlers['selection-change'];

		unmount();

		expect(editor.off).toHaveBeenCalledWith('text-change', textHandler);
		expect(editor.off).toHaveBeenCalledWith('selection-change', selectionHandler);
	});
});
