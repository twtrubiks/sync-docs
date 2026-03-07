import { get, type User } from '$lib/auth';

// 文檔型別
export interface Document {
	id: string;
	title: string;
	is_owner: boolean;
	owner: User;
	permission: 'read' | 'write' | null;
	can_write: boolean;
}

// 分頁文檔列表回應
export interface PaginatedDocumentResponse {
	items: Document[];
	total: number;
	page: number;
	page_size: number;
	total_pages: number;
}

// 取得文檔列表（支援分頁）
export async function getDocuments(
	page: number = 1,
	pageSize: number = 20
): Promise<PaginatedDocumentResponse> {
	return get(
		`/documents/?page=${page}&page_size=${pageSize}`
	) as Promise<PaginatedDocumentResponse>;
}
