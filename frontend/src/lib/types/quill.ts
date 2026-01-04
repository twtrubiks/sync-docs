import type Quill from 'quill';

// Re-export Quill instance type
export type QuillType = Quill;

// Delta operation type (matches Quill's Op type structure)
export interface DeltaOperation {
	insert?: string | Record<string, unknown>;
	delete?: number;
	retain?: number | Record<string, unknown>;
	attributes?: Record<string, unknown>;
}

// QuillDelta - compatible with both plain objects and Quill's Delta class
// This is a structural type that works for both input (plain objects) and output (Delta instances)
export interface QuillDelta {
	ops: DeltaOperation[];
}
