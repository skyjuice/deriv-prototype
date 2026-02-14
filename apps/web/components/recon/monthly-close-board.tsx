"use client";

import Link from "next/link";
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import type { MonthlyCloseBatch } from "@/lib/types";

type Props = {
  items: MonthlyCloseBatch[];
};

type ActionName = "journal" | "submit";

function stateClass(item: MonthlyCloseBatch) {
  if (item.submitted_to_erp) return "bg-emerald-100 text-emerald-700";
  if (item.ready_for_erp) return "bg-orange-100 text-orange-700";
  return "bg-rose-100 text-rose-700";
}

function sourceRunClass(doubtfulTransactions: number, notifiedToSource: boolean) {
  if (doubtfulTransactions <= 0) {
    return "border-emerald-300 bg-emerald-50 text-emerald-700";
  }
  if (notifiedToSource) {
    return "border-amber-300 bg-amber-50 text-amber-700";
  }
  return "border-rose-300 bg-rose-50 text-rose-700";
}

function sourceRunStatusText(doubtfulTransactions: number, notifiedToSource: boolean) {
  if (doubtfulTransactions <= 0) {
    return "No issues";
  }
  if (notifiedToSource) {
    return "Issue handled";
  }
  return "Issue pending";
}

export function MonthlyCloseBoard({ items }: Props) {
  const router = useRouter();
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [errorByMonth, setErrorByMonth] = useState<Record<string, string>>({});
  const [isPending, startTransition] = useTransition();

  function runAction(month: string, action: ActionName) {
    const key = `${month}:${action}`;
    setPendingKey(key);
    setErrorByMonth((prev) => ({ ...prev, [month]: "" }));

    startTransition(() => {
      void (async () => {
        try {
          const response = await fetch(`/api/v1/monthly-close/${encodeURIComponent(month)}/${action}`, { method: "POST" });
          const payload = await response.json().catch(() => ({ error: "Action failed" }));
          if (!response.ok) {
            throw new Error(payload.error || "Action failed");
          }
          router.refresh();
        } catch (error) {
          setErrorByMonth((prev) => ({ ...prev, [month]: (error as Error).message }));
        } finally {
          setPendingKey(null);
        }
      })();
    });
  }

  return (
    <section className="rounded-xl border bg-card p-4">
      <h2 className="mb-3 font-medium">Monthly Close (ERP Submission)</h2>
      <p className="mb-4 text-xs text-muted-foreground">
        Monthly close aggregates only daily-closed runs. Journal and ERP submission happen here, not in daily BAU.
      </p>
      <div className="space-y-3">
        {items.length === 0 ? <p className="text-sm text-muted-foreground">No monthly batches available yet. Close daily runs first.</p> : null}
        {items.map((item) => {
          const canJournal = item.ready_for_erp && !item.journal_created && !item.submitted_to_erp && item.good_transactions > 0;
          const notificationsReady = item.doubtful_notification_sent >= item.doubtful_notification_required;
          const canSubmit =
            item.ready_for_erp &&
            notificationsReady &&
            !item.submitted_to_erp &&
            (item.good_transactions === 0 || item.journal_created);
          return (
            <article key={item.month} className="rounded-lg border p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <p className="font-mono text-xs">{item.month}</p>
                <span className={`rounded-full px-2 py-1 text-[11px] ${stateClass(item)}`}>{item.next_action}</span>
              </div>

              <div className="mb-3 grid gap-2 text-xs md:grid-cols-6">
                <div className="rounded border p-2"><p className="text-muted-foreground">Closed Runs</p><p className="font-medium">{item.source_run_count}</p></div>
                <div className="rounded border p-2"><p className="text-muted-foreground">Total Txn</p><p className="font-medium">{item.total_transactions}</p></div>
                <div className="rounded border p-2"><p className="text-muted-foreground">Good</p><p className="font-medium text-emerald-700">{item.good_transactions}</p></div>
                <div className="rounded border p-2"><p className="text-muted-foreground">Doubtful</p><p className="font-medium text-rose-700">{item.doubtful_transactions}</p></div>
                <div className="rounded border p-2"><p className="text-muted-foreground">PSP Notified</p><p className="font-medium">{item.doubtful_notification_sent}/{item.doubtful_notification_required}</p></div>
                <div className="rounded border p-2"><p className="text-muted-foreground">Ready</p><p className="font-medium">{item.ready_for_erp ? "yes" : "no"}</p></div>
              </div>

              <details className="mb-3 rounded border bg-muted/20 p-2 text-xs">
                <summary className="cursor-pointer font-medium">Source Runs ({item.source_runs.length})</summary>
                <div className="mt-2 flex flex-wrap gap-2">
                  {item.source_runs.length === 0 ? <span className="text-muted-foreground">No closed runs yet.</span> : null}
                  {item.source_runs.map((sourceRun) => (
                    <Link
                      key={`${item.month}-${sourceRun.run_id}`}
                      href={`/runs/${sourceRun.run_id}`}
                      className={`rounded border px-2 py-1 ${sourceRunClass(sourceRun.doubtful_transactions, sourceRun.notified_to_source)}`}
                    >
                      <span className="font-mono">{sourceRun.run_number}</span> • {sourceRun.business_date} •{" "}
                      {sourceRunStatusText(sourceRun.doubtful_transactions, sourceRun.notified_to_source)}
                    </Link>
                  ))}
                </div>
              </details>

              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => runAction(item.month, "journal")}
                  disabled={!canJournal || isPending}
                  className="rounded border px-2 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {pendingKey === `${item.month}:journal` ? "Working..." : "Create Journal"}
                </button>
                <button
                  onClick={() => runAction(item.month, "submit")}
                  disabled={!canSubmit || isPending}
                  className="rounded bg-primary px-2 py-1 text-xs text-primary-foreground disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {pendingKey === `${item.month}:submit` ? "Working..." : "Submit to ERP"}
                </button>
              </div>

              <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                {item.doubtful_notification_required > 0 && !notificationsReady ? (
                  <span className="rounded border border-amber-300 bg-amber-50 px-2 py-0.5 text-amber-700">
                    Send PSP notification before ERP submission
                  </span>
                ) : null}
                {item.journal_created_at ? <span className="rounded border px-2 py-0.5">Journal: {item.journal_created_at}</span> : null}
                {item.submitted_at ? <span className="rounded border px-2 py-0.5">Submitted: {item.submitted_at}</span> : null}
              </div>

              {errorByMonth[item.month] ? <p className="mt-2 text-xs text-rose-700">{errorByMonth[item.month]}</p> : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}
