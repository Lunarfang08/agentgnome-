import Link from "next/link";
import { cookies } from "next/headers";
import { api, endpoint } from "./api";
import { login, logout, operate } from "./actions";

const example = JSON.stringify(
  {
    apiVersion: "agentgenome.io/v1",
    kind: "AgentGenome",
    metadata: { name: "procurement-demo", version: "1.0.0" },
    spec: {
      model: { route: "deterministic-procurement" },
      tools: { allowed: ["inventory.read", "orders.prepare", "orders.submit"] },
      sandbox: { profile: "trusted-fixture" },
      limits: { maxCostUsd: "1.00" },
      evaluation: { suite: "procurement-integrity@1.0.0" },
    },
  },
  null,
  2,
);
type Run = {
  id: string;
  state: string;
  task: string;
  actual_cost: string;
  genome_hash: string;
};
type Approval = {
  id: string;
  run_id: string;
  arguments_hash: string;
  expires_at: string;
};
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  const token = (await cookies()).get("ag_session")?.value;
  let data: {
    me: { subject: string; profile: string; scopes: string[] };
    runs: { items: Run[] };
    approvals: { items: Approval[] };
  } | null = null;
  let failure = error;
  if (token) {
    try {
      const [me, runs, approvals] = await Promise.all([
        api<{ subject: string; profile: string; scopes: string[] }>("/me"),
        api<{ items: Run[] }>("/runs"),
        api<{ items: Approval[] }>("/approvals"),
      ]);
      data = { me, runs, approvals };
    } catch (e) {
      failure = e instanceof Error ? e.message : "Service unavailable";
    }
  }
  let health = "unavailable";
  try {
    const r = await fetch(endpoint + "/readyz", {
      cache: "no-store",
      signal: AbortSignal.timeout(6000),
    });
    health = r.ok ? "ready" : "dependencies unavailable";
  } catch {}
  return (
    <main>
      <header>
        <div className="brand">
          <span className="mark">AG</span>
          <div>
            AgentGenome<small>GOVERNED AGENT RUNTIME</small>
          </div>
        </div>
        <div className="status">Control plane · {health}</div>
      </header>
      <div className="intro">
        <p className="eyebrow">WORKSPACE / CONTROL PLANE</p>
        <h1>Execution with evidence.</h1>
        <p>
          Version behavior. Inspect execution. Approve every simulated write.
        </p>
      </div>
      {failure && (
        <p role="alert" className="error">
          {failure}
        </p>
      )}
      {!data ? (
        <section className="login">
          <h2>Connect your workspace</h2>
          <p>
            Use a scoped API token or your configured development token. The
            token stays in a server-only session cookie.
          </p>
          <form action={login}>
            <label>
              Access token
              <input name="token" type="password" autoComplete="off" required />
            </label>
            <button>Connect</button>
          </form>
        </section>
      ) : (
        <>
          <div className="toolbar">
            <span className="badge">
              {data.me.profile} · deterministic simulated services
            </span>
            <span>{data.me.subject}</span>
            <form action={logout}>
              <button className="secondary">Sign out</button>
            </form>
          </div>
          <div className="grid stats">
            <section>
              <small>LOADED RUNS</small>
              <strong>{data.runs.items.length}</strong>
            </section>
            <section>
              <small>SUCCEEDED IN LOADED RUNS</small>
              <strong>
                {data.runs.items.filter((r) => r.state === "SUCCEEDED").length}
              </strong>
            </section>
            <section>
              <small>PENDING APPROVALS (UP TO 100)</small>
              <strong>{data.approvals.items.length}</strong>
            </section>
          </div>
          <section>
            <div className="section-title">
              <h2>Run explorer</h2>
              <Link href="/">Refresh</Link>
            </div>
            {data.runs.items.length ? (
              <div className="scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Task / run</th>
                      <th>State</th>
                      <th>Recorded cost</th>
                      <th>Evidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.runs.items.map((r) => (
                      <tr key={r.id}>
                        <td>
                          {r.task}
                          <small>{r.id}</small>
                        </td>
                        <td>
                          <span className="badge">{r.state}</span>
                        </td>
                        <td>${r.actual_cost}</td>
                        <td>
                          <Link href={`/runs/${r.id}`}>Inspect trace →</Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p>
                No runs yet. Publish a genome below to start the simulated
                workflow.
              </p>
            )}
          </section>
          <section>
            <h2>Approval inbox</h2>
            {!data.approvals.items.length && <p>No pending approvals.</p>}
            {data.approvals.items.map((a) => (
              <article key={a.id}>
                <p>Simulated purchase order · {a.run_id}</p>
                <small>Bound argument digest: {a.arguments_hash}</small>
                <p>Expires {a.expires_at}</p>
                {data.me.scopes.includes("approve") && (
                  <form action={operate}>
                    <input type="hidden" name="id" value={a.id} />
                    <button name="action" value="approve">
                      Approve simulated order
                    </button>
                    <button className="secondary" name="action" value="reject">
                      Reject
                    </button>
                  </form>
                )}
              </article>
            ))}
          </section>
          {data.me.scopes.includes("write") && (
            <section>
              <h2>Publish & execute</h2>
              <p>
                This profile uses a deterministic model and trusted fixture
                tools. No external purchase is made.
              </p>
              <form action={operate}>
                <input type="hidden" name="action" value="create" />
                <label>
                  Agent name
                  <input
                    name="name"
                    defaultValue="Procurement demonstration"
                    required
                    maxLength={100}
                  />
                </label>
                <label>
                  Genome manifest
                  <textarea
                    name="manifest"
                    defaultValue={example}
                    rows={16}
                    required
                  />
                </label>
                <button>Publish genome and start run</button>
              </form>
            </section>
          )}
        </>
      )}
      <footer>
        AgentGenome · development increment · production execution is disabled
      </footer>
    </main>
  );
}
