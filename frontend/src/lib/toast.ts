import { toast } from '@zerodevx/svelte-toast';

/** 統一 Toast 色彩主題 */
const themes = {
	success: {
		'--toastBackground': '#22c55e',
		'--toastColor': 'white',
		'--toastBarBackground': '#16a34a'
	},
	error: {
		'--toastBackground': '#ef4444',
		'--toastColor': 'white',
		'--toastBarBackground': '#dc2626'
	},
	warning: {
		'--toastBackground': '#f59e0b',
		'--toastColor': 'white',
		'--toastBarBackground': '#d97706'
	}
} as const;

export function toastSuccess(msg: string) {
	toast.push(msg, { theme: themes.success });
}

export function toastError(msg: string) {
	toast.push(msg, { theme: themes.error });
}

export function toastWarning(msg: string) {
	toast.push(msg, { theme: themes.warning });
}
