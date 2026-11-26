"use server";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { api, endpoint } from "./api";

export async function login(form: FormData) {
  const token = String(form.get("token") || "");
  const response = await fetch(endpoint + "/api/v1/me", {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
    signal: AbortSignal.timeout(6000),
  });
  if (!response.ok) redirect("/?error=Invalid%20credentials");
  (await cookies()).set("ag_session", token, {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.AG_PROFILE === "production",
    path: "/",
    maxAge: 3600,
  });
  redirect("/");
}
export async function logout() {
  (await cookies()).delete("ag_session");
  redirect("/");
}
export async function operate(form: FormData) {
  const action = String(form.get("action"));
  try {
    if (action === "create") {
      const agent = await api<{ id: string }>("/agents", {
        method: "POST",
        body: JSON.stringify({ name: form.get("name") }),
      });
      const manifest = JSON.parse(String(form.get("manifest")));
      const genome = await api<{ id: string }>(`/agents/${agent.id}/genomes`, {
        method: "POST",
        body: JSON.stringify(manifest),
      });
      await api(`/genomes/${genome.id}/publish`, { method: "POST" });
      await api("/runs", {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({
          genome_id: genome.id,
          task: "Prepare and submit an approved simulated order",
        }),
      });
    } else if (action === "approve" || action === "reject") {
      await api(
        `/approvals/${encodeURIComponent(String(form.get("id")))}/${action}`,
        { method: "POST" },
      );
    } else if (action === "cancel") {
      await api(`/runs/${encodeURIComponent(String(form.get("id")))}/cancel`, {
        method: "POST",
      });
    } else throw new Error("Unknown action");
  } catch (error) {
    redirect(
      "/?error=" +
        encodeURIComponent(
          error instanceof SyntaxError
            ? "Genome must contain valid JSON"
            : error instanceof Error
              ? error.message
              : "Request failed",
        ),
    );
  }
  revalidatePath("/");
  redirect("/");
}
