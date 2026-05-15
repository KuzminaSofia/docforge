import { cache } from "react";
import { redirect } from "next/navigation";
import { serverFetch } from "@/lib/api/server";
import type { UserResponse } from "@/lib/api/types";
import { UnauthorizedError } from "@/lib/api/errors";

// Дедуплицирует запрос /users/me в рамках одного серверного рендера,
// поэтому layout и page могут оба вызывать getRequiredUser без лишних HTTP-запросов.
const fetchCurrentUser = cache(async (): Promise<UserResponse | null> => {
  try {
    return await serverFetch<UserResponse>("/users/me");
  } catch (err) {
    if (err instanceof UnauthorizedError) return null;
    throw err;
  }
});

export async function getCurrentUser(): Promise<UserResponse | null> {
  return fetchCurrentUser();
}

export async function getRequiredUser(): Promise<UserResponse> {
  const user = await fetchCurrentUser();
  if (!user) redirect("/login?expired=1");
  return user;
}
