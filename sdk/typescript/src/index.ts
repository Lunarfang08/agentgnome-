import type { components } from "./schema.js";
export type Genome = components["schemas"]["Manifest"];
export type RunInput = components["schemas"]["RunInput"];

export class AgentGenomeClient {
  constructor(
    private baseUrl: string,
    private token: string,
  ) {}
  async request(
    path: string,
    init: RequestInit = {},
  ): Promise<Record<string, unknown>> {
    const response = await fetch(
      this.baseUrl.replace(/\/$/, "") + "/api/v1/" + path.replace(/^\//, ""),
      {
        ...init,
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.token}`,
          ...init.headers,
        },
        redirect: "error",
        signal: init.signal ?? AbortSignal.timeout(10000),
      },
    );
    if (!response.ok)
      throw new Error(`AgentGenome API error ${response.status}`);
    return response.json();
  }
  run(body: RunInput, idempotencyKey: string) {
    return this.request("runs", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(body),
    });
  }
}
