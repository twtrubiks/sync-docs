import { get, post, put, del } from '$lib/auth';

// ============ 評論相關型別 ============

/**
 * 評論
 */
export interface Comment {
	id: string;
	content: string;
	author_username: string;
	created_at: string;
	updated_at: string;
	parent_id: string | null;
	reply_count: number;
	is_author: boolean; // 當前用戶是否為作者（可編輯）
	can_delete: boolean; // 當前用戶是否可刪除（作者或文件擁有者）
}

/**
 * 評論列表回應
 */
export interface CommentListResponse {
	comments: Comment[];
	total: number;
}

/**
 * 創建評論請求
 */
export interface CommentCreatePayload {
	content: string;
	parent_id?: string;
}

/**
 * 編輯評論請求
 */
export interface CommentUpdatePayload {
	content: string;
}

// ============ API 函數 ============

/**
 * 取得評論列表（頂層評論）
 */
export async function getComments(documentId: string): Promise<CommentListResponse> {
	return get(`/documents/${documentId}/comments/`) as Promise<CommentListResponse>;
}

/**
 * 取得評論的回覆列表
 */
export async function getReplies(documentId: string, commentId: string): Promise<Comment[]> {
	return get(`/documents/${documentId}/comments/${commentId}/replies/`) as Promise<Comment[]>;
}

/**
 * 創建評論或回覆
 */
export async function createComment(
	documentId: string,
	payload: CommentCreatePayload
): Promise<Comment> {
	return post(`/documents/${documentId}/comments/`, payload) as Promise<Comment>;
}

/**
 * 編輯評論
 */
export async function updateComment(
	documentId: string,
	commentId: string,
	payload: CommentUpdatePayload
): Promise<Comment> {
	return put(`/documents/${documentId}/comments/${commentId}/`, payload) as Promise<Comment>;
}

/**
 * 刪除評論
 */
export async function deleteComment(
	documentId: string,
	commentId: string
): Promise<{ success: boolean; message: string }> {
	return del(`/documents/${documentId}/comments/${commentId}/`) as Promise<{
		success: boolean;
		message: string;
	}>;
}
