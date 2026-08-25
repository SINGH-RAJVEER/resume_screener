import { Button } from "@skillsignal/ui/components/button";
import { useEffect, useState } from "react";
import {
	candidateClient,
	type OrderResponse,
	type PointPack,
	type PointQuote,
	type PointsSummary,
} from "./client";

type RazorpayOptions = Record<string, unknown>;

declare global {
	interface Window {
		Razorpay?: new (
			options: Record<string, unknown>,
		) => { open: () => void };
	}
}

const loadCheckoutScript = () =>
	new Promise<void>((resolve, reject) => {
		if (window.Razorpay) return resolve();
		const script = document.createElement("script");
		script.src = "https://checkout.razorpay.com/v1/checkout.js";
		script.onload = () => resolve();
		script.onerror = () =>
			reject(new Error("Payment checkout could not be loaded"));
		document.head.appendChild(script);
	});

export const formatResetDate = (iso: string) =>
	new Date(iso).toLocaleDateString(undefined, {
		weekday: "long",
		month: "short",
		day: "numeric",
	});

export const usePointsSummary = () => {
	const [points, setPoints] = useState<PointsSummary | null>(null);
	const [quote, setQuote] = useState<PointQuote | null>(null);

	useEffect(() => {
		candidateClient
			.points()
			.then(setPoints)
			.catch(() => setPoints(null));
		candidateClient
			.quote()
			.then(setQuote)
			.catch(() => setQuote(null));
	}, []);

	return {
		points,
		quote,
		refreshPoints: () => void candidateClient.points().then(setPoints),
	};
};

export const BillingStrip = ({
	points,
	quote,
}: {
	points: PointsSummary | null;
	quote: PointQuote | null;
}) => {
	if (!points && !quote) return null;
	return (
		<div className="billing-strip">
			{points?.allowance && (
				<span>
					{points.allowance.freeUsedThisWeek
						? `Free check used · returns ${formatResetDate(points.allowance.resetsAt)}`
						: "Your free weekly check is available"}
				</span>
			)}
			{points && <span>{`${points.balance} point balance`}</span>}
			{quote && (
				<span>{`A paid check reserves up to ${quote.points} points`}</span>
			)}
		</div>
	);
};

export const PackPurchase = ({
	packs,
	onPurchased,
}: {
	packs: PointPack[];
	onPurchased: () => void;
}) => {
	const [buyingPackId, setBuyingPackId] = useState<string | null>(null);
	const [error, setError] = useState<string | null>(null);

	const buy = async (packId: string) => {
		setBuyingPackId(packId);
		setError(null);
		try {
			await loadCheckoutScript();
			const order: OrderResponse =
				await candidateClient.createOrder(packId);
			if (!window.Razorpay)
				throw new Error("Payment checkout unavailable");
			const checkout = new window.Razorpay({
				key: order.razorpayKeyId,
				order_id: order.razorpayOrderId,
				amount: order.amountInr * 100,
				currency: order.currency,
				name: "SkillSignal points",
				description: `${order.points} points`,
				prefill: {},
				theme: { color: "#111111" },
				handler: async (response: {
					razorpay_order_id: string;
					razorpay_payment_id: string;
					razorpay_signature: string;
				}) => {
					try {
						await candidateClient.verifyCheckout(
							order.id,
							response.razorpay_payment_id,
							response.razorpay_signature,
						);
						onPurchased();
					} catch (reason) {
						setError(
							reason instanceof Error
								? reason.message
								: "The payment could not be confirmed",
						);
					}
				},
			} as RazorpayOptions);
			checkout.open();
		} catch (reason) {
			setError(
				reason instanceof Error ? reason.message : "Purchase failed",
			);
		} finally {
			setBuyingPackId(null);
		}
	};

	return (
		<div className="pack-purchase">
			<h3>Buy points</h3>
			<p className="form-hint">
				One-time payments through Razorpay in Indian Rupees. Points land
				as soon as the payment webhook is processed.
			</p>
			<ul className="pack-list">
				{packs.map((pack) => (
					<li key={pack.id}>
						<span>{`${pack.points.toLocaleString()} points`}</span>
						<Button
							disabled={buyingPackId !== null}
							onClick={() => void buy(pack.id)}
							size="sm"
							variant="outline"
						>
							{buyingPackId === pack.id
								? "Opening checkout"
								: `₹${pack.amountInr}`}
						</Button>
					</li>
				))}
			</ul>
			{error && (
				<p className="form-error" role="alert">
					{error}
				</p>
			)}
		</div>
	);
};
