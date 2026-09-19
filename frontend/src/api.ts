import i18n from "./i18n";
import { DEMO_TOKEN, getMockResponse } from "./mockData";

const TOKEN_KEY = "grc.token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();

  // If in demo mock mode, directly return realistic mock data
  if (token === DEMO_TOKEN) {
    const mock = getMockResponse(path, init, i18n.language);
    if (mock !== undefined) {
      return mock as T;
    }
  }

  const response = await fetch(path, {
    ...init,
    headers: {
      ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
  });

  if (response.status === 401) {
    setToken(null);
    throw new ApiError(401, "unauthorized", i18n.t("common.unauthorized"));
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body.code ?? "error", body.message ?? i18n.t("common.requestFailed"));
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

export async function download(path: string): Promise<Blob> {
  const token = getToken();
  if (token === DEMO_TOKEN) {
    return new Blob(["Demo document content"], { type: "text/plain" });
  }
  const response = await fetch(path, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (response.status === 401) {
    setToken(null);
    throw new ApiError(401, "unauthorized", i18n.t("common.unauthorized"));
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body.code ?? "error", body.message ?? i18n.t("common.requestFailed"));
  }
  return response.blob();
}
