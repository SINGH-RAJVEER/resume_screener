export type PointPack = { id: string; points: number; amountInr: number };

export type OrderResponse = {
	id: string;
	razorpayOrderId: string;
	razorpayKeyId: string;
	amountInr: number;
	currency: string;
	packId: string;
	points: number;
};

export type PointsSummary = {
	scope: string;
	balance: number;
	available: number;
	organizationId?: string;
	enterprise?: boolean;
	allowance?: {
		freeUsedThisWeek: boolean;
		resetsAt: string;
	};
};
