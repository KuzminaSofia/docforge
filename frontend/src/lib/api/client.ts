import { extractErrorDetail, throwForStatus, UnauthorizedError } from "./errors";
import { buildApiUrl } from "@/lib/utils";

const BASE = "/api";

type FetchOptions = Omit<RequestInit, "body"> & {
  params?: Record<string, string | number | boolean | null | undefined>;
  body?: RequestInit["body"] | Record<string, unknown>;
};

async function clientRequest(path: string, options: FetchOptions = {}): Promise<Response> {
  const { params, body, headers: extraHeaders, ...init } = options;
  const url = buildApiUrl(BASE, path, params);

  const isFormData = body instanceof FormData;
  const contentType = isFormData ? undefined : "application/json";
  const serializedBody = isFormData
    ? body
    : body !== undefined
      ? JSON.stringify(body)
      : undefined;

  const res = await fetch(url, {
    ...init,
    body: serializedBody,
    credentials: "include",
    headers: {
      ...(contentType ? { "Content-Type": contentType } : {}),
      ...(extraHeaders as Record<string, string>),
    },
  });

  if (!res.ok) {
    const detail = await extractErrorDetail(res);
    throwForStatus(res.status, detail);
  }

  return res;
}

/**
 * Client-side fetch for use in Client Components.
 * Uses relative /api path (proxied via nginx to FastAPI).
 * Sends cookies automatically (same-origin credentials).
 */
export async function clientFetch<T>(path: string, options: FetchOptions = {}): Promise<T> {
  return (await clientRequest(path, options)).json() as Promise<T>;
}

export async function clientFetchText(path: string, options: FetchOptions = {}): Promise<string> {
  return (await clientRequest(path, options)).text();
}

/**
 * Проверяет, является ли ошибка признаком истёкшей / отсутствующей сессии.
 * Используй в обработчиках ошибок Client Components для редиректа на /login.
 */
export function isUnauthorized(err: unknown): err is UnauthorizedError {
  return err instanceof UnauthorizedError;
}
