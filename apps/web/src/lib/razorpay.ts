type RazorpayCheckout = { open: () => void };

declare global {
	interface Window {
		Razorpay?: new (options: Record<string, unknown>) => RazorpayCheckout;
	}
}

let checkoutScript: Promise<void> | null = null;

const loadCheckout = () => {
	checkoutScript ??= new Promise<void>((resolve, reject) => {
		if (window.Razorpay) return resolve();
		const script = document.createElement("script");
		script.src = "https://checkout.razorpay.com/v1/checkout.js";
		script.onload = () => resolve();
		script.onerror = () =>
			reject(new Error("Payment checkout could not be loaded"));
		document.head.appendChild(script);
	});
	return checkoutScript;
};

export type CheckoutHandlerResponse = {
	razorpay_order_id: string;
	razorpay_payment_id: string;
	razorpay_signature: string;
};

export type CheckoutSession = {
	key: string;
	orderId: string;
	amountPaise: number;
	currency: string;
	name: string;
	description: string;
	handler: (response: CheckoutHandlerResponse) => void;
};

export const openCheckout = async (session: CheckoutSession) => {
	await loadCheckout();
	if (!window.Razorpay) throw new Error("Payment checkout unavailable");
	const checkout = new window.Razorpay({
		key: session.key,
		order_id: session.orderId,
		amount: session.amountPaise,
		currency: session.currency,
		name: session.name,
		description: session.description,
		theme: { color: "#111111" },
		handler: session.handler,
	});
	checkout.open();
};
