"use client";

import Link from "next/link";
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import type { DailyOpsSummary } from "@/lib/types";

type Props = {
  items: DailyOpsSummary[];
};

type ActionName = "address-doubtful" | "notify" | "close";

function closeBadge(state: string) {
  if (state === "closed") return "bg-emerald-100 text-emerald-700";
  if (state === "ready_to_close") return "bg-orange-100 text-orange-700";
  return "bg-rose-100 text-rose-700";
}

export function DailyOpsBoard({ items }: Props) {
  const router = useRouter();
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [errorByRun, setErrorByRun] = useState<Record<string, string>>({});
  const [isPending, startTransition] = useTransition();

  function runAction(runId: string, action: ActionName) {
    const key = `${runId}:${action}`;
    setPendingKey(key);
    setErrorByRun((prev) => ({ ...prev, [runId]: "" }));

    startTransition(() => {
      void (async () => {
        try {
          const response = await fetch(`/api/v1/daily-ops/${runId}/${action}`, { method: "POST" });
          const payload = await response.json().catch(() => ({ error: "Action failed" }));
          if (!response.ok) {
            throw new Error(payload.error || "Action failed");
          }
          router.refresh();
        } catch (error) {
          setErrorByRun((prev) => ({ ...prev, [runId]: (error as Error).message }));
        } finally {
          setPendingKey(null);
        }
      })();
    });
  }

  return (
    <section className="rounded-xl border bg-card p-4">
      <h2 className="mb-3 font-medium">Daily BAU Operations</h2>
      <p className="mb-4 text-xs text-muted-foreground">
        Daily automation runs reconciliation. Human-on-the-loop only addresses doubtful records, sends notifications, and closes the day.
      </p>
      <div className="space-y-3">
        {items.length === 0 ? <p className="text-sm text-muted-foreground">No daily runs available.</p> : null}
        {items.map((item) => (
          <article key={item.run_id} className="rounded-lg border p-3">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="font-mono text-xs">{item.run_id.slice(0, 8)}</p>
                <p className="text-xs text-muted-foreground">Business date: {item.business_date}</p>
              </div>
              <span className={`rounded-full px-2 py-1 text-[11px] ${closeBadge(item.close_state)}`}>{item.close_state}</span>
            </div>

            <div className="mb-3 grid gap-2 text-xs md:grid-cols-6">
              <div className="rounded border p-2"><p className="text-muted-foreground">Run Status</p><p className="font-medium">{item.run_status}</p></div>
              <div className="rounded border p-2"><p className="text-muted-foreground">Total</p><p className="font-medium">{item.total_transactions}</p></div>
              <div className="rounded border p-2"><p className="text-muted-foreground">Good</p><p className="font-medium text-emerald-700">{item.good_transactions}</p></div>
              <div className="rounded border p-2"><p className="text-muted-foreground">Doubtful</p><p className="font-medium text-rose-700">{item.doubtful_transactions}</p></div>
              <div className="rounded border p-2"><p className="text-muted-foreground">Unresolved</p><p className="font-medium">{item.unresolved_doubtful}</p></div>
              <div className="rounded border p-2"><p className="text-muted-foreground">Notifications</p><p className="font-medium">{item.notifications_sent}/{item.notifications_required}</p></div>
            </div>

            {item.notification_targets.length > 0 ? (
              <details className="mb-3 rounded border bg-muted/20 p-2 text-xs">
                <summary className="cursor-pointer font-medium">Notification Targets ({item.notification_targets.length})</summary>
                <div className="mt-2 space-y-1">
                  {item.notification_targets.map((target) => (
                    <p key={`${item.run_id}-${target.recipient_key}`} className="text-muted-foreground">
                      {target.recipient_label}: {target.count} ({target.merchant_refs.join(", ")})
                    </p>
                  ))}
                </div>
              </details>
            ) : null}

            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => runAction(item.run_id, "address-doubtful")}
                disabled={isPending || item.unresolved_doubtful <= 0 || item.run_status !== "completed"}
                className="rounded border px-2 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-50"
              >
                {pendingKey === `${item.run_id}:address-doubtful` ? "Working..." : "Address Doubtful"}
              </button>
              <button
                onClick={() => runAction(item.run_id, "notify")}
                disabled={isPending || item.notifications_required <= item.notifications_sent || item.unresolved_doubtful > 0}
                className="rounded border px-2 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-50"
              >
                {pendingKey === `${item.run_id}:notify` ? "Working..." : "Send Notifications"}
              </button>
              <button
                onClick={() => runAction(item.run_id, "close")}
                disabled={isPending || item.close_state !== "ready_to_close"}
                className="rounded bg-primary px-2 py-1 text-xs text-primary-foreground disabled:cursor-not-allowed disabled:opacity-50"
              >
                {pendingKey === `${item.run_id}:close` ? "Working..." : "Close Daily Run"}
              </button>
              <Link href={`/runs/${item.run_id}`} className="rounded border px-2 py-1 text-xs">
                View Run Details
              </Link>
            </div>

            <p className="mt-2 text-xs text-muted-foreground">Next action: {item.next_action}</p>
            {item.closed_at ? <p className="mt-1 text-xs text-muted-foreground">Closed at: {item.closed_at}</p> : null}
            {errorByRun[item.run_id] ? <p className="mt-2 text-xs text-rose-700">{errorByRun[item.run_id]}</p> : null}
          </article>
        ))}
      </div>
    </section>
  );
}
