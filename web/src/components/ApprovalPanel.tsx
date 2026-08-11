import { useState } from "react";

import type { Approval } from "../types";

interface ApprovalPanelProps {
  approvals: Approval[];
  onDecision: (id: string, approved: boolean, scope: "once" | "task") => Promise<void>;
}

export function ApprovalPanel({ approvals, onDecision }: ApprovalPanelProps) {
  const [pending, setPending] = useState(false);
  if (approvals.length === 0) return null;

  async function decide(id: string, approved: boolean, scope: "once" | "task") {
    setPending(true);
    try { await onDecision(id, approved, scope); } finally { setPending(false); }
  }

  return <section aria-label="approvals"><h2>Approvals</h2>{approvals.map((approval) => <article key={approval.id}><p>{approval.reason}</p><button disabled={pending} onClick={() => decide(approval.id, true, "once")}>Allow once</button><button disabled={pending} onClick={() => decide(approval.id, true, "task")}>Allow for task</button><button disabled={pending} onClick={() => decide(approval.id, false, "once")}>Reject</button></article>)}</section>;
}
