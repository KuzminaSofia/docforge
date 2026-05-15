import { headers } from "next/headers";
import { extractErrorDetail, throwForStatus } from "./errors";
import { buildApiUrl } from "@/lib/utils";

const BASE = process.env.INTERNAL_API_URL ?? "http://app:8000";

type FetchOptions = Omit<RequestInit, "body"> & {
  params?: Record<string, string | number | boolean | null | undefined>;
  body?: RequestInit["body"] | Record<string, unknown>;
};

/**
 * Server-side fetch for use in Server Components and Route Handlers.
 * Forwards the incoming request's cookie to FastAPI so the JWT is passed through.
 */
export async function serverFetch<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const { params, body, headers: extraHeaders, ...init } = options;
  const url = buildApiUrl(BASE, path, params);

  const incomingHeaders = await headers();
  const cookie = incomingHeaders.get("cookie") ?? "";

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
    headers: {
      ...(contentType ? { "Content-Type": contentType } : {}),
      Cookie: cookie,
      ...(extraHeaders as Record<string, string>),
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const detail = await extractErrorDetail(res);
    throwForStatus(res.status, detail);
  }

  return res.json() as Promise<T>;
}
