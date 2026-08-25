import { Button } from "@skillsignal/ui/components/button";
import { X } from "lucide-react";
import { useEffect, useState } from "react";
import { actLabel, type TourStep } from "./types";

const TARGET_WAIT_MS = 3_000;
const POLL_INTERVAL_MS = 120;
const CARD_WIDTH = 344;
const CARD_MARGIN = 16;

type Rect = {
	top: number;
	left: number;
	width: number;
	height: number;
	bottom: number;
};

const measure = (target?: string): Rect | null => {
	if (!target) return null;
	const element = document.querySelector(`[data-tour="${target}"]`);
	if (element === null) return null;
	const rect = element.getBoundingClientRect();
	if (rect.width === 0 && rect.height === 0) return null;
	return {
		top: rect.top,
		left: rect.left,
		width: rect.width,
		height: rect.height,
		bottom: rect.bottom,
	};
};

export const TourOverlay = ({
	step,
	stepIndex,
	stepCount,
	onNext,
	onBack,
	onExit,
}: {
	step: TourStep;
	stepIndex: number;
	stepCount: number;
	onNext: () => void;
	onBack: () => void;
	onExit: () => void;
}) => {
	const [rect, setRect] = useState<Rect | null>(() => measure(step.target));

	useEffect(() => {
		let elapsed = 0;
		setRect(measure(step.target));
		const interval = window.setInterval(() => {
			elapsed += POLL_INTERVAL_MS;
			const found = measure(step.target);
			if (found) {
				setRect(found);
				window.clearInterval(interval);
				return;
			}
			setRect(null);
			if (elapsed >= TARGET_WAIT_MS) window.clearInterval(interval);
		}, POLL_INTERVAL_MS);
		const remeasure = () => setRect(measure(step.target));
		window.addEventListener("resize", remeasure);
		window.addEventListener("scroll", remeasure, true);
		return () => {
			window.clearInterval(interval);
			window.removeEventListener("resize", remeasure);
			window.removeEventListener("scroll", remeasure);
		};
	}, [step]);

	useEffect(() => {
		const onKeyDown = (event: KeyboardEvent) => {
			if (event.key === "Escape") onExit();
		};
		window.addEventListener("keydown", onKeyDown);
		return () => window.removeEventListener("keydown", onKeyDown);
	}, [onExit]);

	const cardStyle = placement(rect);

	return (
		// The root blocks page interaction while the tour is active; only the
		// narration card and its controls accept input.
		<div aria-label="Guided demo" className="tour-overlay" role="dialog">
			{rect !== null && (
				<div
					className="tour-spotlight"
					style={{
						height: rect.height + 8,
						left: rect.left - 4,
						top: rect.top - 4,
						width: rect.width + 8,
					}}
				/>
			)}
			<aside className="tour-card" style={cardStyle}>
				<header className="tour-card-head">
					<p className="eyebrow">
						Guided demo · {actLabel(step.act)}
					</p>
					<button
						aria-label="Exit the guided demo"
						className="icon-button"
						onClick={onExit}
						type="button"
					>
						<X />
					</button>
				</header>
				<h3>{step.title}</h3>
				<p>{step.body}</p>
				<footer className="tour-card-actions">
					<small>
						{stepIndex + 1} / {stepCount}
					</small>
					<div className="tour-card-buttons">
						{stepIndex > 0 && (
							<Button
								onClick={onBack}
								size="sm"
								variant="outline"
							>
								Back
							</Button>
						)}
						<Button onClick={onNext} size="sm">
							{stepIndex === stepCount - 1 &&
							step.act === "candidate"
								? "Finish"
								: "Next"}
						</Button>
					</div>
				</footer>
			</aside>
		</div>
	);
};

const placement = (rect: Rect | null) => {
	if (rect === null) {
		return {
			left: `calc(50% - ${CARD_WIDTH / 2}px)`,
			top: "50%",
			transform: "translateY(-50%)",
		};
	}
	const viewportHeight = window.innerHeight;
	const viewportWidth = window.innerWidth;
	// Prefer below the target; flip above when the card would overflow.
	const below = rect.bottom + CARD_MARGIN;
	const aboveTop = Math.max(CARD_MARGIN, rect.top - CARD_MARGIN - 220);
	const top =
		below + 240 < viewportHeight ? below : Math.max(CARD_MARGIN, aboveTop);
	const left = Math.min(
		Math.max(CARD_MARGIN, rect.left),
		viewportWidth - CARD_WIDTH - CARD_MARGIN,
	);
	return { left, top };
};
