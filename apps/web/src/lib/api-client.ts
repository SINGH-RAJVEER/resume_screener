export const baseURL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const safeJson = async (
	response: Response,
): Promise<{ message?: string } | undefined> => {
	try {
		const text = await response.text();
		return text ? (JSON.parse(text) as { message?: string }) : undefined;
	} catch {
		// Non-JSON bodies (proxy error pages) carry no API message.
		return undefined;
	}
};

export const apiRequest = async <T>(
	path: string,
	init?: RequestInit,
): Promise<T> => {
	const response = await fetch(`${baseURL}${path}`, {
		...init,
		headers: {
			...(init?.body instanceof FormData
				? {}
				: { "Content-Type": "application/json" }),
			Authorization: `Bearer ${localStorage.getItem("auth_token") ?? ""}`,
			...init?.headers,
		},
	});
	const body = response.status === 204 ? undefined : await safeJson(response);
	if (!response.ok) {
		throw new Error(body?.message ?? "Request failed");
	}
	return body as T;
};

export const downloadFile = async (
	path: string,
	filename: string,
	failureMessage: string,
) => {
	const response = await fetch(`${baseURL}${path}`, {
		headers: {
			Authorization: `Bearer ${localStorage.getItem("auth_token") ?? ""}`,
		},
	});
	if (!response.ok) throw new Error(failureMessage);
	const blob = await response.blob();
	const url = URL.createObjectURL(blob);
	const anchor = document.createElement("a");
	anchor.href = url;
	anchor.download = filename;
	anchor.click();
	URL.revokeObjectURL(url);
};
