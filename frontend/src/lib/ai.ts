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

// AI 請求超時時間（毫秒）
const AI_REQUEST_TIMEOUT = 30000;

export async function processWithAI(
	request: AIProcessRequest,
	signal?: AbortSignal
): Promise<AIProcessResponse> {
	// 若未提供 signal，自動建立超時控制
	const controller = signal ? null : new AbortController();
	const timeoutId = controller
		? setTimeout(() => controller.abort(), AI_REQUEST_TIMEOUT)
		: null;

	try {
		return await post('/ai/process', request as unknown as Record<string, unknown>, controller?.signal || signal);
	} finally {
		if (timeoutId) clearTimeout(timeoutId);
	}
}
