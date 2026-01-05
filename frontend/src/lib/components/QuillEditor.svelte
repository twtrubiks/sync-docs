<script lang="ts">
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import 'quill/dist/quill.snow.css'; // Import Quill's snow theme CSS
	import type { QuillDelta, QuillType } from '$lib/types/quill';
	import type QuillClass from 'quill';
	import type QuillCursors from 'quill-cursors';

	let editorContainer: HTMLElement;
	let Quill: typeof QuillClass;
	let cursorsModule: QuillCursors | null = null;

	// Svelte 5 Runes: $props() with $bindable() for two-way binding
	let {
		value = $bindable({ ops: [] }),
		editor = $bindable(),
		onTextChange,
		onSelectionChange,
		disabled = false
	}: {
		value?: QuillDelta;
		editor?: QuillType;
		onTextChange?: (detail: { delta: QuillDelta; source: string }) => void;
		onSelectionChange?: (range: { index: number; length: number } | null) => void;
		disabled?: boolean;
	} = $props();

	onMount(async () => {
		if (browser) {
			// Dynamically import Quill only on the client-side
			const module = await import('quill');
			Quill = module.default;

			// 動態導入 quill-cursors
			const cursorsModuleImport = await import('quill-cursors');
			const QuillCursorsClass = cursorsModuleImport.default;
			Quill.register('modules/cursors', QuillCursorsClass);

			editor = new Quill(editorContainer, {
				theme: 'snow',
				modules: {
					cursors: {
						hideDelayMs: 5000, // 5 秒無活動後隱藏游標
						hideSpeedMs: 300, // 隱藏動畫速度
						selectionChangeSource: null,
						transformOnTextChange: true
					},
					toolbar: [
						[{ header: [1, 2, 3, false] }],
						['bold', 'italic', 'underline', 'strike'],
						[{ list: 'ordered' }, { list: 'bullet' }],
						['link', 'image'],
						['clean']
					]
				}
			});

			// 獲取 cursors 模組實例
			cursorsModule = editor.getModule('cursors') as QuillCursors;

			// Set initial content. This is crucial because the `value` prop
			// might have been updated by the parent component while Quill was loading.
			if (value && value.ops && value.ops.length > 0) {
				editor.setContents(value.ops, 'silent');
			}

			// 定義事件處理函數（需要保存引用以便正確移除）
			const textChangeHandler = (
				delta: QuillDelta,
				_oldDelta: QuillDelta,
				source: string
			) => {
				// Always update the bound value
				if (editor) {
					value = editor.getContents();
				}
				// Call the callback prop instead of dispatching an event
				onTextChange?.({ delta, source });
			};

			const selectionChangeHandler = (
				range: { index: number; length: number } | null,
				_oldRange: unknown,
				source: string
			) => {
				if (source === 'user' && onSelectionChange && range) {
					onSelectionChange(range);
				}
			};

			// 監聽文字變化
			editor.on('text-change', textChangeHandler);

			// 新增：監聽游標變化
			editor.on('selection-change', selectionChangeHandler);

			// 返回 cleanup 函數，在組件卸載時清理事件監聽器
			return () => {
				if (editor) {
					editor.off('text-change', textChangeHandler);
					editor.off('selection-change', selectionChangeHandler);
				}
			};
		}
	});

	// 游標操作方法（透過暴露的函數讓父組件呼叫）
	export function setCursor(
		userId: string,
		username: string,
		color: string,
		range: { index: number; length: number }
	) {
		if (cursorsModule) {
			const cursor = cursorsModule.cursors().find((c: { id: string }) => c.id === userId);
			if (!cursor) {
				cursorsModule.createCursor(userId, username, color);
			}
			cursorsModule.moveCursor(userId, range);
		}
	}

	export function removeCursor(userId: string) {
		if (cursorsModule) {
			cursorsModule.removeCursor(userId);
		}
	}

	// Svelte 5 Runes: $effect() replaces $: reactive statement
	$effect(() => {
		// When the value prop changes from the parent, update the editor's content
		if (editor && value && value.ops) {
			// A simple stringify comparison to prevent infinite update loops
			if (JSON.stringify(value) !== JSON.stringify(editor.getContents())) {
				editor.setContents(value.ops, 'silent');
			}
		}
	});

	// Handle disabled prop changes
	$effect(() => {
		if (editor) {
			editor.enable(!disabled);
		}
	});
</script>

<div class="quill-container" bind:this={editorContainer}></div>

<style>
	.quill-container :global(.ql-toolbar) {
		border-top-left-radius: 0.5rem;
		border-top-right-radius: 0.5rem;
		border-bottom: 1px solid #ccc;
	}
	.quill-container :global(.ql-container) {
		border-bottom-left-radius: 0.5rem;
		border-bottom-right-radius: 0.5rem;
		font-size: 16px;
		position: relative; /* 必須：讓 quill-cursors 的絕對定位正確工作 */
	}
	.quill-container :global(.ql-editor) {
		min-height: 750px; /* A4-like height */
		padding: 2rem;
		line-height: 1.6;
	}
	/* quill-cursors 樣式 */
	.quill-container :global(.ql-cursors) {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		pointer-events: none;
		overflow: hidden;
	}
	.quill-container :global(.ql-cursor) {
		position: absolute;
	}
	.quill-container :global(.ql-cursor-caret-container) {
		position: absolute;
		height: 100%;
	}
	.quill-container :global(.ql-cursor-caret) {
		position: absolute;
		width: 2px;
		height: 100%;
		/* 讓游標更明顯 */
		box-shadow: 0 0 2px currentColor;
	}
	.quill-container :global(.ql-cursor-flag) {
		position: absolute;
		top: -1.5em;
		left: -1px;
		padding: 2px 6px;
		font-size: 12px;
		white-space: nowrap;
		border-radius: 3px;
		color: white;
		font-weight: 500;
		/* 保持 flag 可見 */
		visibility: visible !important;
		opacity: 1 !important;
		transition: none !important;
	}
	.quill-container :global(.ql-cursor-selection-block) {
		position: absolute;
		opacity: 0.3;
	}
</style>
