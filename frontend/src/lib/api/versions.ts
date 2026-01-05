import { get, post } from '$lib/auth';

// 版本相關型別
export interface DocumentVersion {
	id: string;
	version_number: number;
	created_at: string;
	created_by_username: string | null;
}

export interface DocumentVersionDetail extends DocumentVersion {
	content: Record<string, unknown>;
}

export interface RestoreVersionResponse {
	success: boolean;
	message: string;
	new_version_number: number;
}

// 取得版本列表
export async function getVersions(documentId: string): Promise<DocumentVersion[]> {
	return get(`/documents/${documentId}/versions/`) as Promise<DocumentVersion[]>;
}

// 取得版本詳情
export async function getVersionDetail(
	documentId: string,
	versionId: string
): Promise<DocumentVersionDetail> {
	return get(`/documents/${documentId}/versions/${versionId}/`) as Promise<DocumentVersionDetail>;
}

// 還原版本
export async function restoreVersion(
	documentId: string,
	versionId: string
): Promise<RestoreVersionResponse> {
	return post(
		`/documents/${documentId}/versions/${versionId}/restore/`,
		{}
	) as Promise<RestoreVersionResponse>;
}
