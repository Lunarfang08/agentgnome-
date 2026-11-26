import Link from "next/link";
import { api } from "../../api";
import { operate } from "../../actions";
export default async function Run({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  try {
    const run = await api<{
      id: string;
      state: string;
      checkpoint: unknown;
      result: unknown;
      genome_hash: string;
    }>(`/runs/${encodeURIComponent(id)}`);
    return (
      <main>
        <Link href="/">← Workspace</Link>
        <h1>Run evidence</h1>
        <p>{run.id}</p>
        <p className="badge">{run.state}</p>
        <section>
          <h2>Pinned genome</h2>
          <code>{run.genome_hash}</code>
        </section>
        <section>
          <h2>Persisted checkpoint</h2>
          <pre>{JSON.stringify(run.checkpoint, null, 2)}</pre>
        </section>
        <section>
          <h2>Result</h2>
          <pre>{JSON.stringify(run.result, null, 2)}</pre>
        </section>
        {![
          "SUCCEEDED",
          "FAILED",
          "CANCELLED",
          "TIMED_OUT",
          "BUDGET_EXHAUSTED",
        ].includes(run.state) && (
          <form action={operate}>
            <input type="hidden" name="action" value="cancel" />
            <input type="hidden" name="id" value={id} />
            <button>Cancel run</button>
          </form>
        )}
      </main>
    );
  } catch {
    return (
      <main>
        <Link href="/">← Workspace</Link>
        <h1>Run unavailable</h1>
        <p>The run could not be loaded or you do not have access.</p>
      </main>
    );
  }
}
