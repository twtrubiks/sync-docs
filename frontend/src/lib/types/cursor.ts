/**
 * 游標位置
 */
export interface CursorPosition {
	index: number; // Quill 游標位置（字符索引）
	length: number; // 選取長度（0 = 只有游標）
}

/**
 * 在線用戶資訊
 */
export interface PresenceUser {
	user_id: string;
	username: string;
	color: string;
	cursor?: CursorPosition;
}
