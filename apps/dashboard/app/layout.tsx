import type { Metadata } from "next";
import "./style.css";
export const metadata: Metadata = {
  title: "AgentGenome · Control plane",
  description: "Governed agent execution",
};
export default function Layout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
