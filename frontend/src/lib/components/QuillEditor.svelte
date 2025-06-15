<script lang="ts">
  import { onMount, createEventDispatcher } from 'svelte';
  import { browser } from '$app/environment';
  import 'quill/dist/quill.snow.css'; // Import Quill's snow theme CSS

  let editorContainer: HTMLElement;
  let Quill: any;

  export let value: any = { ops: [] };
  export let editor: Quill; // Expose the Quill instance

  const dispatch = createEventDispatcher();

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
            ['clean'],
          ],
        },
      });

      // Set initial content. This is crucial because the `value` prop
      // might have been updated by the parent component while Quill was loading.
      if (value && value.ops && value.ops.length > 0) {
        editor.setContents(value, 'silent');
      }

      editor.on('text-change', (delta, oldDelta, source) => {
        // Always update the bound value
        value = editor.getContents();
        // Dispatch an event with the delta and source for the parent to handle
        dispatch('text-change', { delta, source });
      });
    }
  });

  // When the value prop changes from the parent, update the editor's content
  $: if (editor && value && value.ops) {
    // A simple stringify comparison to prevent infinite update loops
    if (JSON.stringify(value) !== JSON.stringify(editor.getContents())) {
      editor.setContents(value, 'silent');
    }
  }
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
