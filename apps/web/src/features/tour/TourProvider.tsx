import {
	createContext,
	type ReactNode,
	useCallback,
	useContext,
	useEffect,
	useMemo,
	useRef,
	useState,
} from "react";
import { authClient } from "../../lib/auth-client";
import { TourOverlay } from "./TourOverlay";
import type { TourAct, TourActions, TourStep } from "./types";

const ACT_KEY = "skillsignal-demo-act";
const INDEX_KEY = "skillsignal-demo-index";
const USER_KEY = "skillsignal-demo-user";

export const accountTypeForAct = (act: TourAct) =>
	act === "employer" ? "employer" : "candidate";

type TourState = { act: TourAct; index: number } | null;

interface TourContextValue {
	state: TourState;
	steps: TourStep[];
	next: () => void;
	back: () => void;
	exit: () => void;
	getActions: () => TourActions;
}

const TourContext = createContext<TourContextValue | null>(null);

const RegisterContext = createContext<
	(id: string, actions: TourActions | null) => void
>(() => {});

/**
 * Surfaces register the imperative handles tour steps need. Registration is
 * per component id because a parent (CandidateHome) and its child
 * (PrivateEvaluationWorkspace) both contribute actions.
 */
export const useRegisterTourActions = (
	id: string,
	actions: TourActions,
): void => {
	const register = useContext(RegisterContext);
	useEffect(() => {
		register(id, actions);
		return () => register(id, null);
	});
};

export const useTour = (): TourContextValue => {
	const value = useContext(TourContext);
	if (!value) throw new Error("useTour requires TourProvider");
	return value;
};

export const TourProvider = ({
	children,
	steps,
	sessionUserId,
	sessionAccountType,
}: {
	children: ReactNode;
	steps: TourStep[];
	/** Changing user identity re-evaluates whether a saved demo run resumes. */
	sessionUserId?: string;
	sessionAccountType?: string;
}) => {
	const [state, setState] = useState<TourState>(null);
	const registries = useRef(new Map<string, TourActions>());
	const stateRef = useRef<TourState>(null);
	stateRef.current = state;

	const register = useCallback((id: string, actions: TourActions | null) => {
		if (actions === null) registries.current.delete(id);
		else registries.current.set(id, actions);
	}, []);

	const getActions = useCallback((): TourActions => {
		const merged: TourActions = {};
		for (const partial of registries.current.values()) {
			Object.assign(merged, partial);
		}
		return merged;
	}, []);

	const persist = useCallback((next: TourState, userId?: string) => {
		if (next === null) {
			sessionStorage.removeItem(ACT_KEY);
			sessionStorage.removeItem(INDEX_KEY);
			sessionStorage.removeItem(USER_KEY);
			return;
		}
		sessionStorage.setItem(ACT_KEY, next.act);
		sessionStorage.setItem(INDEX_KEY, String(next.index));
		if (userId) sessionStorage.setItem(USER_KEY, userId);
	}, []);

	const beginAct = useCallback(
		(act: TourAct, userId?: string) => {
			persist({ act, index: 0 }, userId);
			setState({ act, index: 0 });
			void authClient.demo(act);
		},
		[persist],
	);

	// Resume an interrupted run only for the same user and account type.
	useEffect(() => {
		if (state !== null || !sessionUserId) return;
		const savedAct = sessionStorage.getItem(ACT_KEY);
		if (savedAct !== "employer" && savedAct !== "candidate") return;
		if (sessionStorage.getItem(USER_KEY) !== sessionUserId) return;
		if (accountTypeForAct(savedAct) !== sessionAccountType) return;
		setState({
			act: savedAct,
			index: Number(sessionStorage.getItem(INDEX_KEY) ?? "0"),
		});
	}, [sessionUserId, sessionAccountType, state]);

	const exit = useCallback(() => {
		persist(null);
		setState(null);
	}, [persist]);

	const next = useCallback(() => {
		const current = stateRef.current;
		if (current === null) return;
		const actSteps = steps.filter((step) => step.act === current.act);
		if (current.index < actSteps.length - 1) {
			const moved = { ...current, index: current.index + 1 };
			persist(moved);
			setState(moved);
			return;
		}
		// The employer act hands off to the candidate act; the candidate act ends.
		if (current.act === "employer") beginAct("candidate", sessionUserId);
		else exit();
	}, [beginAct, exit, persist, sessionUserId, steps]);

	const back = useCallback(() => {
		const current = stateRef.current;
		if (current === null || current.index === 0) return;
		const moved = { ...current, index: current.index - 1 };
		persist(moved);
		setState(moved);
	}, [persist]);

	// Run each step's prepare once per activation. The guard lives inside so
	// freshly registered handles are always read at activation time.
	const preparedStepId = useRef<string | null>(null);
	useEffect(() => {
		const active = stepFor(steps, state);
		if (!active || active.id === preparedStepId.current) return;
		preparedStepId.current = active.id;
		active.prepare?.(getActions());
	});

	const value = useMemo(
		() => ({
			state,
			steps,
			next,
			back,
			exit,
			getActions,
		}),
		[state, steps, next, back, exit, getActions],
	);

	const activeStep = stepFor(steps, state);

	return (
		<TourContext.Provider value={value}>
			<RegisterContext.Provider value={register}>
				{children}
				{state !== null && activeStep !== null && (
					<TourOverlay
						onBack={back}
						onExit={exit}
						onNext={next}
						step={activeStep}
						stepCount={
							steps.filter((step) => step.act === state.act)
								.length
						}
						stepIndex={state.index}
					/>
				)}
			</RegisterContext.Provider>
		</TourContext.Provider>
	);
};

const stepFor = (
	steps: TourStep[],
	state: { act: TourAct; index: number } | null,
): TourStep | null =>
	state === null
		? null
		: (steps.filter((step) => step.act === state.act)[state.index] ?? null);
