import { post } from '$lib/auth';

// AI HTTP API（校對 / 文件分析）。摘要、潤稿與文件問答走 WebSocket 串流，
// 見文件頁 +page.svelte 的 startAIStream / startAskStream。

// 結構化校對（proofread）
export interface WritingIssue {
	original: string;
	suggestion: string;
	reason: string;
	severity: 'info' | 'warning' | 'error';
}

export interface ProofreadResult {
	issues: WritingIssue[];
	overall_score: number;
}

export interface ProofreadResponse {
	success: boolean;
	result?: ProofreadResult;
	error?: string;
}

// 文件 metadata
export interface DocumentMetadata {
	summary: string;
	tags: string[];
	language: string;
	reading_time: number;
}

export interface MetadataResponse {
	success: boolean;
	result?: DocumentMetadata;
	error?: string;
}

// AI 請求超時時間（毫秒）
const AI_REQUEST_TIMEOUT = 30000;

export async function proofreadWithAI(
	text: string,
	signal?: AbortSignal
): Promise<ProofreadResponse> {
	// 若未提供 signal，自動建立超時控制
	const controller = signal ? null : new AbortController();
	const timeoutId = controller ? setTimeout(() => controller.abort(), AI_REQUEST_TIMEOUT) : null;

	try {
		return await post('/ai/proofread', { text }, controller?.signal || signal);
	} finally {
		if (timeoutId) clearTimeout(timeoutId);
	}
}

export async function metadataWithAI(
	text: string,
	signal?: AbortSignal
): Promise<MetadataResponse> {
	// 若未提供 signal，自動建立超時控制
	const controller = signal ? null : new AbortController();
	const timeoutId = controller ? setTimeout(() => controller.abort(), AI_REQUEST_TIMEOUT) : null;

	try {
		return await post('/ai/metadata', { text }, controller?.signal || signal);
	} finally {
		if (timeoutId) clearTimeout(timeoutId);
	}
}
