import { Button } from "@skillsignal/ui/components/button";
import { useEffect, useState } from "react";
import { openCheckout } from "../../lib/razorpay";
import {
	candidateClient,
	type OrderResponse,
	type PointPack,
	type PointQuote,
	type PointsSummary,
} from "./client";

const formatResetDate = (iso: string) =>
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
		refreshPoints: () =>
			void candidateClient
				.points()
				.then(setPoints)
				.catch(() => setPoints(null)),
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
		<div className="billing-strip" data-tour="billing-strip">
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
			const order: OrderResponse =
				await candidateClient.createOrder(packId);
			await openCheckout({
				key: order.razorpayKeyId,
				orderId: order.razorpayOrderId,
				amountPaise: order.amountInr * 100,
				currency: order.currency,
				name: "SkillSignal points",
				description: `${order.points} points`,
				handler: async (response) => {
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
			});
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
