import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function buildApiUrl(
  base: string,
  path: string,
  params?: Record<string, string | number | boolean | null | undefined>,
): string {
  const url = base.replace(/\/$/, "") + (path.startsWith("/") ? path : "/" + path);
  if (!params) return url;
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v != null) qs.set(k, String(v));
  }
  const queryString = qs.toString();
  return queryString ? `${url}?${queryString}` : url;
}
