import { post } from '$lib/auth';

// AI 相關 API
export interface AIProcessRequest {
	action: 'summarize' | 'polish';
	text: string;
}

export interface AIProcessResponse {
	success: boolean;
	result: string;
	action: string;
	error?: string;
}

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

// 文件問答
export interface AskResponse {
	success: boolean;
	answer?: string;
	error?: string;
}

// AI 請求超時時間（毫秒）
const AI_REQUEST_TIMEOUT = 30000;

// 註：摘要/潤稿已改走 WebSocket 串流逐字輸出（DocConsumer 的 ai_stream，commit 0e0c775），
// 前端 UI 不再呼叫此函式。保留為 REST 對等 API（後端有測試），暫不移除以縮小改動範圍。
export async function processWithAI(
	request: AIProcessRequest,
	signal?: AbortSignal
): Promise<AIProcessResponse> {
	// 若未提供 signal，自動建立超時控制
	const controller = signal ? null : new AbortController();
	const timeoutId = controller ? setTimeout(() => controller.abort(), AI_REQUEST_TIMEOUT) : null;

	try {
		return await post(
			'/ai/process',
			request as unknown as Record<string, unknown>,
			controller?.signal || signal
		);
	} finally {
		if (timeoutId) clearTimeout(timeoutId);
	}
}

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

// 註：文件問答已改走 WebSocket 串流逐字輸出（DocConsumer 的 ai_ask_stream，commit 952e0e7），
// 前端 UI 不再呼叫此函式。保留為 REST 對等 API（後端有測試），暫不移除以縮小改動範圍。
export async function askWithAI(
	question: string,
	documentText: string,
	signal?: AbortSignal
): Promise<AskResponse> {
	// 若未提供 signal，自動建立超時控制
	const controller = signal ? null : new AbortController();
	const timeoutId = controller ? setTimeout(() => controller.abort(), AI_REQUEST_TIMEOUT) : null;

	try {
		return await post(
			'/ai/ask',
			{ question, document_text: documentText },
			controller?.signal || signal
		);
	} finally {
		if (timeoutId) clearTimeout(timeoutId);
	}
}
