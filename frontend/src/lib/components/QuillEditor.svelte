<script lang="ts">
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import 'quill/dist/quill.snow.css'; // Import Quill's snow theme CSS
	import type { QuillDelta, QuillType } from '$lib/types/quill';
	import type QuillClass from 'quill';

	let editorContainer: HTMLElement;
	let Quill: typeof QuillClass;

	// Svelte 5 Runes: $props() with $bindable() for two-way binding
	let {
		value = $bindable({ ops: [] }),
		editor = $bindable(),
		onTextChange,
		disabled = false
	}: {
		value?: QuillDelta;
		editor?: QuillType;
		onTextChange?: (detail: { delta: QuillDelta; source: string }) => void;
		disabled?: boolean;
	} = $props();

	onMount(async () => {
		if (browser) {
			// Dynamically import Quill only on the client-side
			const module = await import('quill');
			Quill = module.default;

			editor = new Quill(editorContainer, {
				theme: 'snow',
				modules: {
					toolbar: [
						[{ header: [1, 2, 3, false] }],
						['bold', 'italic', 'underline', 'strike'],
						[{ list: 'ordered' }, { list: 'bullet' }],
						['link', 'image'],
						['clean']
					]
				}
			});

			// Set initial content. This is crucial because the `value` prop
			// might have been updated by the parent component while Quill was loading.
			if (value && value.ops && value.ops.length > 0) {
				editor.setContents(value.ops, 'silent');
			}

			editor.on('text-change', (delta: QuillDelta, _oldDelta: QuillDelta, source: string) => {
				// Always update the bound value
				if (editor) {
					value = editor.getContents();
				}
				// Call the callback prop instead of dispatching an event
				onTextChange?.({ delta, source });
			});
		}
	});

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
	}
	.quill-container :global(.ql-editor) {
		min-height: 750px; /* A4-like height */
		padding: 2rem;
		line-height: 1.6;
	}
</style>
