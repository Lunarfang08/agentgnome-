import "server-only";
import { cookies } from "next/headers";
export const endpoint = process.env.API_URL || "http://127.0.0.1:8080";
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const token = (await cookies()).get("ag_session")?.value;
  const response = await fetch(endpoint + "/api/v1" + path, {
    ...init,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token || ""}`,
      ...init?.headers,
    },
    signal: AbortSignal.timeout(6000),
  });
  if (!response.ok) {
    const problem = await response.json().catch(() => ({}));
    throw new Error(
      `${response.status}: ${problem.detail || "API unavailable"}`,
    );
  }
  return response.json() as Promise<T>;
}
