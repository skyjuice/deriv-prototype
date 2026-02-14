"use client";

import Link from "next/link";
import { useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { RiAlarmWarningLine, RiCalendarCheckLine, RiNotification3Line } from "@remixicon/react";

import type { MonthlySubmission } from "@/lib/types";

type Props = {
  runId: string;
  items: MonthlySubmission[];
};

type ActionName = "address-doubtful" | "notify";

function StepPill({ label, active, done }: { label: string; active: boolean; done: boolean }) {
  const cls = done
    ? "border-emerald-500 bg-emerald-50 text-emerald-700"
    : active
      ? "border-orange-400 bg-orange-50 text-orange-700"
      : "border-muted bg-muted/40 text-muted-foreground";
  return <span className={`inline-flex items-center rounded-full border px-2 py-1 text-[11px] ${cls}`}>{label}</span>;
}

function actionLabel(action: ActionName) {
  if (action === "address-doubtful") return "Address Doubtful";
  return "Notify Source Teams";
}

function actionIcon(action: ActionName) {
  if (action === "address-doubtful") return <RiAlarmWarningLine size={14} />;
  return <RiNotification3Line size={14} />;
}

function labelFromRecipient(recipient: string) {
  if (recipient === "psp_provider") return "PSP Provider";
  if (recipient === "internal_backoffice") return "Internal Backoffice";
  if (recipient === "cashier_erp") return "Backoffice";
  return "Reconciliation Ops";
}

function stateClass(state: string) {
  if (["resolved", "approved"].includes(state)) return "bg-emerald-100 text-emerald-700";
  if (["verified"].includes(state)) return "bg-orange-100 text-orange-700";
  return "bg-rose-100 text-rose-700";
}

export function MonthlySubmissionBoard({ runId, items }: Props) {
  const router = useRouter();
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [errorByMonth, setErrorByMonth] = useState<Record<string, string>>({});
  const [isPending, startTransition] = useTransition();

  const sorted = useMemo(() => [...items].sort((a, b) => a.month.localeCompare(b.month)), [items]);

  function runAction(month: string, action: ActionName) {
    const key = `${month}:${action}`;
    setPendingKey(key);
    setErrorByMonth((prev) => ({ ...prev, [month]: "" }));

    startTransition(() => {
      void (async () => {
        try {
          const response = await fetch(
            `/api/v1/runs/${runId}/monthly-submissions/${encodeURIComponent(month)}/${action}`,
            { method: "POST" },
          );
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
    <section className="mb-4 rounded-xl border bg-card p-4">
      <div className="mb-3 flex items-center gap-2">
        <RiCalendarCheckLine size={16} />
        <h2 className="font-medium">Daily Exception Handling (Per Month)</h2>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        Daily team handles doubtful records and notifications here. Monthly journal + ERP submission is handled in the separate Monthly Close screen.
      </p>
      <div className="mb-3">
        <Link href="/monthly-close" className="rounded border px-2 py-1 text-xs">
          Go to Monthly Close
        </Link>
      </div>

      {sorted.length === 0 ? <p className="text-xs text-muted-foreground">No monthly buckets available yet.</p> : null}
      <div className="space-y-3">
        {sorted.map((item) => {
          const needsAddressing = item.unresolved_doubtful > 0;
          const canNotify = item.ready_for_submission && item.doubtful_transactions > 0 && !item.notified_to_source && !item.submitted_to_erp;

          return (
            <article key={item.month} className="rounded-lg border p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <p className="font-mono text-xs">{item.month}</p>
                <span
                  className={`rounded-full px-2 py-1 text-[11px] ${
                    item.submitted_to_erp
                      ? "bg-emerald-100 text-emerald-700"
                      : item.ready_for_submission
                        ? "bg-orange-100 text-orange-700"
                        : "bg-rose-100 text-rose-700"
                  }`}
                >
                  {item.submitted_to_erp ? "submitted" : item.ready_for_submission ? "ready" : "blocked"}
                </span>
              </div>

              <div className="mb-3 grid gap-2 text-xs md:grid-cols-5">
                <div className="rounded border p-2">
                  <p className="text-muted-foreground">All Pool</p>
                  <p className="font-semibold">{item.total_transactions}</p>
                </div>
                <div className="rounded border p-2">
                  <p className="text-muted-foreground">Good</p>
                  <p className="font-semibold text-emerald-700">{item.good_transactions}</p>
                </div>
                <div className="rounded border p-2">
                  <p className="text-muted-foreground">Doubtful</p>
                  <p className="font-semibold text-rose-700">{item.doubtful_transactions}</p>
                </div>
                <div className="rounded border p-2">
                  <p className="text-muted-foreground">Addressed</p>
                  <p className="font-semibold">{item.addressed_doubtful}</p>
                </div>
                <div className="rounded border p-2">
                  <p className="text-muted-foreground">Unresolved</p>
                  <p className="font-semibold">{item.unresolved_doubtful}</p>
                </div>
              </div>

              <div className="mb-3 flex flex-wrap items-center gap-2">
                <StepPill label="Address Doubtful" active={item.next_action === "address_doubtful"} done={!needsAddressing} />
                <span className="text-muted-foreground">→</span>
                <StepPill label="Notify Sources" active={item.next_action === "notify_sources"} done={item.notified_to_source || item.doubtful_transactions === 0} />
                <span className="text-muted-foreground">→</span>
                <StepPill label="Close Daily Run" active={item.next_action === "close_day"} done={item.notified_to_source || item.doubtful_transactions === 0} />
                <span className="text-muted-foreground">→</span>
                <StepPill label="Monthly Close Queue" active={item.next_action === "monthly_close"} done={item.notified_to_source || item.doubtful_transactions === 0} />
              </div>

              {item.doubtful_details.length > 0 ? (
                <details className="mb-3 rounded-md border bg-muted/20 p-2">
                  <summary className="cursor-pointer text-xs font-medium">
                    Alert Details ({item.doubtful_details.length}){item.notified_to_source ? " • sent" : " • preview"}
                  </summary>
                  <div className="mt-2 space-y-2 text-xs">
                    <div className="flex flex-wrap gap-2">
                      {item.alert_recipients.length === 0 ? (
                        <span className="rounded border px-2 py-1 text-muted-foreground">No recipients inferred</span>
                      ) : (
                        item.alert_recipients.map((target) => (
                          <div key={`${item.month}-${target.recipient_key}`} className="rounded border bg-card px-2 py-1">
                            <p className="font-medium">{target.recipient_label}: {target.count}</p>
                            <p className="text-muted-foreground">{target.reason}</p>
                            <p className="text-muted-foreground">Refs: {target.merchant_refs.join(", ")}</p>
                          </div>
                        ))
                      )}
                    </div>

                    <div className="overflow-x-auto rounded border">
                      <table className="w-full min-w-[700px] text-left text-xs">
                        <thead className="border-b bg-muted/40 text-muted-foreground">
                          <tr>
                            <th className="px-2 py-1">Merchant Ref</th>
                            <th className="px-2 py-1">Missing Source</th>
                            <th className="px-2 py-1">Reason</th>
                            <th className="px-2 py-1">Target</th>
                            <th className="px-2 py-1">State</th>
                          </tr>
                        </thead>
                        <tbody>
                          {item.doubtful_details.map((detail) => (
                            <tr key={`${item.month}-${detail.merchant_ref}`} className="border-b align-top">
                              <td className="px-2 py-1 font-mono">{detail.merchant_ref}</td>
                              <td className="px-2 py-1">{detail.missing_sources.length ? detail.missing_sources.join(", ") : "-"}</td>
                              <td className="px-2 py-1 text-muted-foreground">{detail.reason_codes.join(", ") || "-"}</td>
                              <td className="px-2 py-1 text-muted-foreground">{detail.recipients.map(labelFromRecipient).join(", ")}</td>
                              <td className="px-2 py-1">
                                <span className={`rounded-full px-2 py-0.5 ${stateClass(detail.state)}`}>{detail.state}</span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </details>
              ) : null}

              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => runAction(item.month, "address-doubtful")}
                  disabled={!needsAddressing || isPending}
                  className="inline-flex items-center gap-1 rounded border px-2 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {actionIcon("address-doubtful")}
                  {pendingKey === `${item.month}:address-doubtful` ? "Working..." : actionLabel("address-doubtful")}
                </button>
                <button
                  onClick={() => runAction(item.month, "notify")}
                  disabled={!canNotify || isPending}
                  className="inline-flex items-center gap-1 rounded border px-2 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {actionIcon("notify")}
                  {pendingKey === `${item.month}:notify` ? "Working..." : actionLabel("notify")}
                </button>
              </div>

              <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                {item.notified_at ? <span className="rounded border px-2 py-0.5">Notified: {item.notified_at}</span> : null}
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
