import Link from "next/link";

import { PageShell } from "@/components/recon/page-shell";
import type { DailyOpsSummary, FeedbackMetrics, MonthlyCloseBatch, Run } from "@/lib/types";

export const dynamic = "force-dynamic";

async function getRuns() {
  try {
    const response = await fetch(`${process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000"}/api/v1/runs`, { cache: "no-store" });
    if (!response.ok) {
      return [];
    }
    const payload = await response.json();
    return (payload.runs || []) as Run[];
  } catch {
    return [] as Run[];
  }
}

async function getFeedbackMetrics() {
  try {
    const response = await fetch(`${process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000"}/api/v1/feedback/metrics`, { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as FeedbackMetrics;
  } catch {
    return null;
  }
}

async function getDailyOps() {
  try {
    const response = await fetch(`${process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000"}/api/v1/daily-ops`, { cache: "no-store" });
    if (!response.ok) {
      return [];
    }
    const payload = await response.json();
    return (payload.items || []) as DailyOpsSummary[];
  } catch {
    return [] as DailyOpsSummary[];
  }
}

async function getMonthlyClose() {
  try {
    const response = await fetch(`${process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000"}/api/v1/monthly-close`, { cache: "no-store" });
    if (!response.ok) {
      return [];
    }
    const payload = await response.json();
    return (payload.items || []) as MonthlyCloseBatch[];
  } catch {
    return [] as MonthlyCloseBatch[];
  }
}

export default async function DashboardPage() {
  const [runs, metrics, dailyOps, monthlyClose] = await Promise.all([
    getRuns(),
    getFeedbackMetrics(),
    getDailyOps(),
    getMonthlyClose(),
  ]);
  const closedDaily = dailyOps.filter((item) => item.close_state === "closed").length;
  const openDaily = dailyOps.filter((item) => item.close_state !== "closed").length;
  const monthlyReady = monthlyClose.filter((item) => item.ready_for_erp && !item.submitted_to_erp).length;
  const monthlySubmitted = monthlyClose.filter((item) => item.submitted_to_erp).length;

  return (
    <PageShell title="Dashboard">
      <div className="mb-4 grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <div className="rounded-xl border bg-card p-4"><p className="text-sm text-muted-foreground">Runs</p><p className="mt-1 text-2xl font-semibold">{runs.length}</p></div>
        <div className="rounded-xl border bg-card p-4"><p className="text-sm text-muted-foreground">Good (latest)</p><p className="mt-1 text-2xl font-semibold">{runs[0]?.counters?.good ?? 0}</p></div>
        <div className="rounded-xl border bg-card p-4"><p className="text-sm text-muted-foreground">Doubtful (latest)</p><p className="mt-1 text-2xl font-semibold">{runs[0]?.counters?.doubtful ?? 0}</p></div>
        <div className="rounded-xl border bg-card p-4"><p className="text-sm text-muted-foreground">Daily Closed</p><p className="mt-1 text-2xl font-semibold">{closedDaily}</p></div>
        <div className="rounded-xl border bg-card p-4"><p className="text-sm text-muted-foreground">Daily Open</p><p className="mt-1 text-2xl font-semibold">{openDaily}</p></div>
        <div className="rounded-xl border bg-card p-4"><p className="text-sm text-muted-foreground">Monthly Ready</p><p className="mt-1 text-2xl font-semibold">{monthlyReady}</p></div>
      </div>

      <section className="mb-6 grid gap-4 md:grid-cols-2">
        <article className="rounded-xl border bg-card p-4">
          <h2 className="font-medium">Daily BAU Track</h2>
          <p className="mt-1 text-sm text-muted-foreground">Upload, reconcile, review non-tally, notify counterparties, then close day.</p>
          <div className="mt-3 flex items-center justify-between text-sm">
            <span>Open daily runs</span>
            <span className="font-semibold">{openDaily}</span>
          </div>
          <Link href="/daily-ops" className="mt-3 inline-block rounded border px-3 py-2 text-sm">Open Daily Ops</Link>
        </article>
        <article className="rounded-xl border bg-card p-4">
          <h2 className="font-medium">Monthly Close Track</h2>
          <p className="mt-1 text-sm text-muted-foreground">Only daily-closed runs are aggregated into monthly journal and ERP submission.</p>
          <div className="mt-3 flex items-center justify-between text-sm">
            <span>Submitted months</span>
            <span className="font-semibold">{monthlySubmitted}</span>
          </div>
          <Link href="/monthly-close" className="mt-3 inline-block rounded border px-3 py-2 text-sm">Open Monthly Close</Link>
        </article>
      </section>

      <section className="mb-6 rounded-xl border bg-card p-4">
        <h2 className="mb-3 font-medium">AI Quality (from UI feedback)</h2>
        {!metrics ? <p className="text-sm text-muted-foreground">No feedback metrics yet.</p> : null}
        {metrics ? (
          <div className="grid gap-4 md:grid-cols-3">
            <div><p className="text-xs text-muted-foreground">Total feedback</p><p className="text-xl font-semibold">{metrics.total_feedback}</p></div>
            <div><p className="text-xs text-muted-foreground">Acceptance rate</p><p className="text-xl font-semibold">{metrics.acceptance_rate}%</p></div>
            <div><p className="text-xs text-muted-foreground">Reject count</p><p className="text-xl font-semibold">{metrics.by_type.reject || 0}</p></div>
          </div>
        ) : null}
        {metrics && metrics.top_reject_reasons.length > 0 ? (
          <div className="mt-4">
            <p className="mb-2 text-xs text-muted-foreground">Top rejection reasons</p>
            <div className="flex flex-wrap gap-2 text-xs">
              {metrics.top_reject_reasons.map((reason) => (
                <span key={reason.reason} className="rounded-full border px-2 py-1">{reason.reason}: {reason.count}</span>
              ))}
            </div>
          </div>
        ) : null}
      </section>

      <div className="mb-6 flex items-center justify-between rounded-xl border bg-card p-4">
        <div>
          <p className="font-medium">Start a new reconciliation run</p>
          <p className="text-sm text-muted-foreground">Upload Internal + ERP + PSP files and execute pipeline.</p>
        </div>
        <Link href="/runs/new" className="rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground">
          New Run
        </Link>
      </div>

      <section className="rounded-xl border bg-card p-4">
        <h2 className="mb-3 font-medium">Recent Runs</h2>
        <div className="space-y-2 text-sm">
          {runs.length === 0 ? <p className="text-muted-foreground">No runs yet.</p> : null}
          {runs.map((run) => (
            <Link key={run.id} href={`/runs/${run.id}`} className="flex items-center justify-between rounded-lg border px-3 py-2 hover:bg-muted">
              <span className="font-mono text-xs">{run.id.slice(0, 8)}</span>
              <span>{run.status}</span>
              <span className="text-muted-foreground">{run.stage}</span>
            </Link>
          ))}
        </div>
      </section>
    </PageShell>
  );
}
