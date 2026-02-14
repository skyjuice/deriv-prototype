import { PageShell } from "@/components/recon/page-shell";
import { MonthlySubmissionBoard } from "@/components/recon/monthly-submission-board";
import type { AIReview, ExceptionItem, MatchDecision, MonthlySubmission, Run } from "@/lib/types";

export const dynamic = "force-dynamic";

type RunData = {
  run: Run | null;
  decisions: MatchDecision[];
  exceptions: ExceptionItem[];
  monthlySubmissions: MonthlySubmission[];
  reviewsByException: Record<string, AIReview[]>;
};

type Stage = {
  name: string;
  pass: number;
  fail: number;
  note: string;
};

async function getRunData(id: string): Promise<RunData> {
  const base = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000";

  const [runResponse, summaryResponse] = await Promise.all([
    fetch(`${base}/api/v1/runs/${id}`, { cache: "no-store" }),
    fetch(`${base}/api/v1/runs/${id}/summary`, { cache: "no-store" }),
  ]);

  const run = runResponse.ok ? ((await runResponse.json()) as Run) : null;
  const summary = summaryResponse.ok ? await summaryResponse.json() : { decisions: [], exceptions: [] };
  const decisions = (summary.decisions || []) as MatchDecision[];
  const exceptions = (summary.exceptions || []) as ExceptionItem[];
  const monthlySubmissions = (summary.monthly_submissions || []) as MonthlySubmission[];

  const reviewEntries = await Promise.all(
    exceptions.map(async (item) => {
      const response = await fetch(`${base}/api/v1/exceptions/${item.id}/reviews`, { cache: "no-store" });
      if (!response.ok) {
        return [item.id, []] as const;
      }
      const payload = await response.json();
      return [item.id, (payload.reviews || []) as AIReview[]] as const;
    }),
  );

  return {
    run,
    decisions,
    exceptions,
    monthlySubmissions,
    reviewsByException: Object.fromEntries(reviewEntries) as Record<string, AIReview[]>,
  };
}

function cx(flag: boolean) {
  return flag ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700";
}

function pct(pass: number, total: number) {
  if (total <= 0) {
    return 0;
  }
  return Math.round((pass / total) * 100);
}

export default async function RunDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await getRunData(id);

  if (!data.run) {
    return (
      <PageShell title="Run Details">
        <p>Run not found.</p>
      </PageShell>
    );
  }

  const total = data.decisions.length;
  const exactPass = data.decisions.filter((d) => d.stage_results.exact_hash).length;
  const fuzzyPass = data.decisions.filter((d) => d.stage_results.fuzzy).length;
  const fuzzyFallbackUsed = data.decisions.filter((d) => !d.stage_results.exact_hash && d.stage_results.fuzzy).length;
  const threeWayPass = data.decisions.filter((d) => d.stage_results.three_way).length;
  const backdatedPass = data.decisions.filter((d) => d.stage_results.backdated).length;
  const fxPass = data.decisions.filter((d) => d.stage_results.fx_handled).length;
  const goodCount = data.decisions.filter((d) => d.final_status === "good_transaction").length;
  const doubtfulCount = data.decisions.filter((d) => d.final_status === "doubtful_transaction").length;

  const pipeline: Stage[] = [
    { name: "Exact Hash", pass: exactPass, fail: total - exactPass, note: "Hash key comparison" },
    { name: "Fuzzy", pass: fuzzyPass, fail: total - fuzzyPass, note: `Fallback rescued ${fuzzyFallbackUsed}` },
    { name: "3-Way", pass: threeWayPass, fail: total - threeWayPass, note: "Presence + amount + identity" },
    { name: "Backdated", pass: backdatedPass, fail: total - backdatedPass, note: "Gap <= 3 days" },
    { name: "FX", pass: fxPass, fail: total - fxPass, note: "Rate completeness / handling" },
    { name: "Final", pass: goodCount, fail: doubtfulCount, note: "Good vs doubtful" },
  ];

  const exceptionByMerchant = new Map(data.exceptions.map((item) => [item.merchant_ref, item]));

  return (
    <PageShell title={`Run ${id.slice(0, 8)}`}>
      <div className="mb-4 grid gap-4 sm:grid-cols-4">
        <div className="rounded-xl border bg-card p-4"><p className="text-sm text-muted-foreground">Status</p><p className="font-medium">{data.run.status}</p></div>
        <div className="rounded-xl border bg-card p-4"><p className="text-sm text-muted-foreground">Stage</p><p className="font-medium">{data.run.stage}</p></div>
        <div className="rounded-xl border bg-card p-4"><p className="text-sm text-muted-foreground">Good</p><p className="font-medium">{goodCount}</p></div>
        <div className="rounded-xl border bg-card p-4"><p className="text-sm text-muted-foreground">Doubtful</p><p className="font-medium">{doubtfulCount}</p></div>
      </div>

      <section className="mb-4 rounded-xl border bg-card p-4">
        <h2 className="mb-3 font-medium">Pipeline Overview</h2>
        <div className="hidden items-center gap-2 lg:flex">
          {pipeline.map((step, index) => (
            <div key={step.name} className="flex items-center gap-2">
              <div className="w-36 rounded-lg border p-3 text-xs">
                <p className="font-medium">{step.name}</p>
                <p className="mt-1 text-muted-foreground">{pct(step.pass, total)}% pass</p>
                <div className="mt-2 h-2 w-full overflow-hidden rounded bg-muted">
                  <div className="h-full bg-emerald-500" style={{ width: `${pct(step.pass, total)}%` }} />
                </div>
              </div>
              {index < pipeline.length - 1 ? <span className="text-muted-foreground">→</span> : null}
            </div>
          ))}
        </div>
        <div className="grid gap-2 lg:hidden md:grid-cols-3">
          {pipeline.map((step) => (
            <div key={step.name} className="rounded-lg border p-3 text-xs">
              <p className="font-medium">{step.name}</p>
              <p className="mt-1 text-muted-foreground">{pct(step.pass, total)}% pass</p>
              <div className="mt-2 h-2 w-full overflow-hidden rounded bg-muted">
                <div className="h-full bg-emerald-500" style={{ width: `${pct(step.pass, total)}%` }} />
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="mb-4 rounded-xl border bg-card p-4">
        <h2 className="mb-3 font-medium">Automation Mode (Human-on-the-Loop)</h2>
        <div className="grid gap-3 md:grid-cols-2">
          <article className="rounded-lg border p-3 text-xs">
            <p className="font-medium">Automated by System</p>
            <p className="mt-1 text-muted-foreground">
              Standardization, exact hash, fuzzy check, 3-way validation, backdated logic, FX handling, and monthly pooling run automatically.
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {pipeline.map((step) => (
                <span key={`${step.name}-auto`} className="rounded-full border px-2 py-1">
                  {step.name}: {step.pass}/{total}
                </span>
              ))}
            </div>
          </article>
          <article className="rounded-lg border p-3 text-xs">
            <p className="font-medium">Human-on-the-Loop Checkpoints</p>
            <p className="mt-1 text-muted-foreground">
              Human only handles exceptions and daily close checks here; monthly ERP approval happens in Monthly Close.
            </p>
            <div className="mt-2 space-y-1 text-muted-foreground">
              <p>Unresolved doubtful: {data.monthlySubmissions.reduce((sum, month) => sum + month.unresolved_doubtful, 0)}</p>
              <p>Months with notifications done: {data.monthlySubmissions.filter((month) => month.notified_to_source).length}</p>
              <p>Monthly close queue candidates: {data.monthlySubmissions.filter((month) => month.ready_for_submission).length}</p>
            </div>
          </article>
        </div>
      </section>

      <MonthlySubmissionBoard runId={id} items={data.monthlySubmissions} />

      <section className="mb-4 rounded-xl border bg-card p-4">
        <h2 className="mb-3 font-medium">Transaction Logic Trace</h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-xs">
            <thead>
              <tr className="border-b text-muted-foreground">
                <th className="px-2 py-2">Merchant Ref</th>
                <th className="px-2 py-2">Exact Hash</th>
                <th className="px-2 py-2">Fuzzy Score</th>
                <th className="px-2 py-2">3-Way</th>
                <th className="px-2 py-2">Backdated</th>
                <th className="px-2 py-2">FX</th>
                <th className="px-2 py-2">Final</th>
                <th className="px-2 py-2">Reason Codes</th>
                <th className="px-2 py-2">Detail</th>
              </tr>
            </thead>
            <tbody>
              {data.decisions.map((decision) => (
                <tr key={decision.merchant_ref} className="border-b align-top">
                  <td className="px-2 py-2 font-mono">
                    <a href={`#trace-${decision.merchant_ref}`} className="underline decoration-dotted underline-offset-2">
                      {decision.merchant_ref}
                    </a>
                  </td>
                  <td className="px-2 py-2">
                    <span className={`rounded-full px-2 py-1 ${cx(decision.stage_results.exact_hash)}`}>
                      {decision.stage_results.exact_hash ? "pass" : "fail"}
                    </span>
                  </td>
                  <td className="px-2 py-2">{decision.fuzzy_score == null ? "n/a" : decision.fuzzy_score.toFixed(2)}</td>
                  <td className="px-2 py-2">
                    <span className={`rounded-full px-2 py-1 ${cx(decision.stage_results.three_way)}`}>
                      {decision.stage_results.three_way ? "pass" : "fail"}
                    </span>
                  </td>
                  <td className="px-2 py-2">
                    <span className={`rounded-full px-2 py-1 ${cx(decision.stage_results.backdated)}`}>
                      {decision.backdated_gap_days == null ? "n/a" : `${decision.backdated_gap_days}d`}
                    </span>
                  </td>
                  <td className="px-2 py-2">
                    <span className={`rounded-full px-2 py-1 ${cx(decision.stage_results.fx_handled)}`}>
                      {decision.fx_detail || (decision.stage_results.fx_handled ? "handled" : "insufficient")}
                    </span>
                  </td>
                  <td className="px-2 py-2">
                    <span className={`rounded-full px-2 py-1 ${decision.final_status === "good_transaction" ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
                      {decision.final_status === "good_transaction" ? "good" : "doubtful"}
                    </span>
                  </td>
                  <td className="px-2 py-2 text-muted-foreground">{decision.reason_codes.length ? decision.reason_codes.join(", ") : "-"}</td>
                  <td className="px-2 py-2">
                    <a href={`#trace-${decision.merchant_ref}`} className="rounded border px-2 py-1 text-[11px] hover:bg-muted">
                      View trace
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mb-4 rounded-xl border bg-card p-4">
        <h2 className="mb-3 font-medium">Per-Transaction Deep Dive</h2>
        <p className="mb-3 text-xs text-muted-foreground">
          Click from the table above or expand any record below to inspect Trinity checks, rule handling, and AI stage outputs.
        </p>
        <div className="space-y-3">
          {data.decisions.map((decision) => {
            const maybeException = exceptionByMerchant.get(decision.merchant_ref);
            const reviews = maybeException ? data.reviewsByException[maybeException.id] || [] : [];
            const trace = (decision.trace_json || {}) as Record<string, unknown>;
            const exact = (trace.exact_hash || {}) as Record<string, unknown>;
            const fuzzy = (trace.fuzzy || {}) as Record<string, unknown>;
            const threeWay = (trace.three_way || {}) as Record<string, unknown>;
            const backdated = (trace.backdated || {}) as Record<string, unknown>;
            const fx = (trace.fx || {}) as Record<string, unknown>;

            return (
              <details key={`trace-${decision.merchant_ref}`} id={`trace-${decision.merchant_ref}`} className="rounded-lg border p-3">
                <summary className="cursor-pointer list-none">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs">{decision.merchant_ref}</span>
                    <span className={`rounded-full px-2 py-1 text-[11px] ${decision.final_status === "good_transaction" ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
                      {decision.final_status === "good_transaction" ? "good" : "doubtful"}
                    </span>
                  </div>
                </summary>

                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  <div className="rounded-md border p-3 text-xs">
                    <p className="font-medium">Trinity (3-Way) Check</p>
                    <p className="mt-1 text-muted-foreground">Presence: {String(threeWay.presence_check ?? "n/a")}</p>
                    <p className="text-muted-foreground">Amount consistency: {String(threeWay.amount_check ?? "n/a")}</p>
                    <p className="text-muted-foreground">Identity consistency: {String(threeWay.identity_check ?? "n/a")}</p>
                  </div>

                  <div className="rounded-md border p-3 text-xs">
                    <p className="font-medium">Exact Hash</p>
                    <p className="mt-1 text-muted-foreground">Matched: {String(exact.matched ?? decision.stage_results.exact_hash)}</p>
                    <p className="text-muted-foreground">Hash samples: {JSON.stringify((exact.hashes || {}) as Record<string, unknown>)}</p>
                  </div>

                  <div className="rounded-md border p-3 text-xs">
                    <p className="font-medium">Fuzzy Logic</p>
                    <p className="mt-1 text-muted-foreground">Score: {decision.fuzzy_score == null ? "n/a" : decision.fuzzy_score.toFixed(2)}</p>
                    <p className="text-muted-foreground">Threshold: {String(fuzzy.threshold ?? "0.90")}</p>
                    <p className="text-muted-foreground">Pair scores: {JSON.stringify((fuzzy.pair_scores || {}) as Record<string, unknown>)}</p>
                  </div>

                  <div className="rounded-md border p-3 text-xs">
                    <p className="font-medium">Backdated + FX</p>
                    <p className="mt-1 text-muted-foreground">Backdated max gap: {decision.backdated_gap_days == null ? "n/a" : `${decision.backdated_gap_days} day(s)`}</p>
                    <p className="text-muted-foreground">Gap details: {JSON.stringify((backdated.pair_gaps_days || {}) as Record<string, unknown>)}</p>
                    <p className="text-muted-foreground">FX handling: {String(fx.detail ?? decision.fx_detail ?? "n/a")}</p>
                  </div>
                </div>

                <div className="mt-3 rounded-md border p-3 text-xs">
                  <p className="font-medium">AI Handling Trace</p>
                  {reviews.length === 0 ? <p className="mt-1 text-muted-foreground">No AI exception review required/available for this transaction.</p> : null}
                  <div className="mt-2 space-y-2">
                    {reviews.map((review) => (
                      <div key={`${decision.merchant_ref}-${review.stage}`} className="rounded border p-2">
                        <p className="font-medium">{review.stage} ({Math.round(review.confidence * 100)}%)</p>
                        <p className="mt-1 text-muted-foreground">{JSON.stringify(review.output_json)}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </details>
            );
          })}
        </div>
      </section>

    </PageShell>
  );
}
