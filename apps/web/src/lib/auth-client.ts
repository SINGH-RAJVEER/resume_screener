import { useEffect, useSyncExternalStore } from "react";

const baseURL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const tokenKey = "auth_token";

interface AuthError {
	code?: string;
	message: string;
}

interface AuthSession {
	user: {
		id: string;
		name: string;
		email: string;
		emailVerified: boolean;
		image?: string | null;
		createdAt: string;
		updatedAt: string;
	};
}

interface AuthResponse extends AuthSession {
	token: string;
	tokenType: "Bearer";
	expiresAt: string;
}

interface AuthState {
	data: AuthSession | null;
	error: AuthError | null;
	isPending: boolean;
}

interface Credentials {
	email: string;
	password: string;
}

interface SignUpCredentials extends Credentials {
	name: string;
}

type AuthResult<T> =
	| { data: T; error: null }
	| { data: null; error: AuthError };
type ParsedResponse =
	| { payload: unknown; error: null }
	| { payload: null; error: AuthError };

let authState: AuthState = { data: null, error: null, isPending: true };
let refreshRequest: Promise<void> | null = null;
const subscribers = new Set<() => void>();

const setAuthState = (nextState: AuthState) => {
	authState = nextState;
	for (const subscriber of subscribers) subscriber();
};

const subscribe = (subscriber: () => void) => {
	subscribers.add(subscriber);
	return () => subscribers.delete(subscriber);
};

const parseResponse = async (response: Response): Promise<ParsedResponse> => {
	try {
		const body = await response.text();
		if (!body) {
			return {
				payload: null,
				error: { message: "The API returned an empty response" },
			};
		}
		return { payload: JSON.parse(body), error: null };
	} catch {
		return {
			payload: null,
			error: { message: "The API returned an invalid response" },
		};
	}
};

const isAuthError = (value: unknown): value is AuthError =>
	typeof value === "object" &&
	value !== null &&
	"message" in value &&
	typeof value.message === "string";

const request = async <T>(
	path: string,
	init?: RequestInit,
): Promise<AuthResult<T>> => {
	let response: Response;
	try {
		const token = localStorage.getItem(tokenKey);
		response = await fetch(`${baseURL}${path}`, {
			...init,
			headers: {
				"Content-Type": "application/json",
				...(token ? { Authorization: `Bearer ${token}` } : {}),
				...init?.headers,
			},
		});
	} catch {
		return { data: null, error: { message: "Unable to reach the API" } };
	}

	const parsed = await parseResponse(response);
	if (parsed.error) return { data: null, error: parsed.error };
	if (!response.ok) {
		return {
			data: null,
			error: isAuthError(parsed.payload)
				? parsed.payload
				: { message: `Request failed with status ${response.status}` },
		};
	}
	return { data: parsed.payload as T, error: null };
};

const refreshSession = () => {
	if (refreshRequest) return refreshRequest;

	refreshRequest = request<AuthSession | null>("/api/auth/session")
		.then((result) => {
			if (!result.data && !result.error) localStorage.removeItem(tokenKey);
			setAuthState({
				data: result.data,
				error: result.error,
				isPending: false,
			});
		})
		.finally(() => {
			refreshRequest = null;
		});
	return refreshRequest;
};

const authenticate = async (
	path: string,
	credentials: Credentials | SignUpCredentials,
) => {
	const result = await request<AuthResponse>(path, {
		method: "POST",
		body: JSON.stringify(credentials),
	});
	if (result.data) {
		localStorage.setItem(tokenKey, result.data.token);
		setAuthState({
			data: { user: result.data.user },
			error: null,
			isPending: false,
		});
	}
	return result;
};

export const authClient = {
	useSession: () => {
		const state = useSyncExternalStore(
			subscribe,
			() => authState,
			() => authState,
		);
		useEffect(() => {
			void refreshSession();
		}, []);
		return state;
	},
	signIn: {
		email: (credentials: Credentials) =>
			authenticate("/api/auth/sign-in/email", credentials),
	},
	signUp: {
		email: (credentials: SignUpCredentials) =>
			authenticate("/api/auth/sign-up/email", credentials),
	},
	signOut: async () => {
		const result = await request<{ success: boolean }>("/api/auth/sign-out", {
			method: "POST",
		});
		localStorage.removeItem(tokenKey);
		setAuthState({ data: null, error: null, isPending: false });
		return result;
	},
};
