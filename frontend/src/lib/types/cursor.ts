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

/**
 * WebSocket 游標移動消息
 */
export interface CursorMoveMessage {
	type: 'cursor_move';
	user_id: string;
	username: string;
	color: string;
	cursor: CursorPosition;
	timestamp: number;
}

/**
 * WebSocket 用戶加入消息
 */
export interface UserJoinMessage {
	type: 'user_join';
	user_id: string;
	username: string;
	color: string;
}

/**
 * WebSocket 用戶離開消息
 */
export interface UserLeaveMessage {
	type: 'user_leave';
	user_id: string;
}

/**
 * WebSocket 在線用戶同步消息
 */
export interface PresenceSyncMessage {
	type: 'presence_sync';
	users: PresenceUser[];
}
