"use client";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main>
      <h1>Workspace unavailable</h1>
      <p role="alert">The control plane could not complete this request.</p>
      <button onClick={reset}>Try again</button>
    </main>
  );
}
