import Link from "next/link";

import { AITracePanel } from "@/components/recon/ai-trace-panel";
import { PageShell } from "@/components/recon/page-shell";
import type { AIReview, ExceptionItem, MatchDecision, Run, TransactionSourceData, TransactionSourceSnapshot } from "@/lib/types";

export const dynamic = "force-dynamic";

type TxData = {
  run: Run | null;
  decision: MatchDecision | null;
  reviews: AIReview[];
  sourceSnapshot: TransactionSourceSnapshot | null;
  exceptionId: string | null;
};

const SOURCE_ORDER = ["internal", "erp", "psp"] as const;

const SOURCE_LABELS: Record<(typeof SOURCE_ORDER)[number], string> = {
  internal: "Cashier",
  erp: "Backoffice",
  psp: "PSP",
};

function decodeMerchantRef(raw: string) {
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

async function getTransactionData(runId: string, rawMerchantRef: string): Promise<TxData> {
  const base = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000";
  const merchantRef = decodeMerchantRef(rawMerchantRef);

  const [runResponse, summaryResponse, sourceSnapshotResponse] = await Promise.all([
    fetch(`${base}/api/v1/runs/${runId}`, { cache: "no-store" }),
    fetch(`${base}/api/v1/runs/${runId}/summary`, { cache: "no-store" }),
    fetch(`${base}/api/v1/runs/${runId}/transactions/${encodeURIComponent(merchantRef)}`, { cache: "no-store" }),
  ]);

  const run = runResponse.ok ? ((await runResponse.json()) as Run) : null;
  const summary = summaryResponse.ok ? await summaryResponse.json() : { decisions: [], exceptions: [] };
  const decisions = (summary.decisions || []) as MatchDecision[];
  const exceptions = (summary.exceptions || []) as ExceptionItem[];
  const sourceSnapshot = sourceSnapshotResponse.ok ? ((await sourceSnapshotResponse.json()) as TransactionSourceSnapshot) : null;

  const decision = decisions.find((item) => item.merchant_ref === merchantRef) || null;
  const exception = exceptions.find((item) => item.merchant_ref === merchantRef) || null;

  let reviews: AIReview[] = [];
  if (exception) {
    const reviewResponse = await fetch(`${base}/api/v1/exceptions/${exception.id}/reviews`, { cache: "no-store" });
    if (reviewResponse.ok) {
      const payload = await reviewResponse.json();
      reviews = (payload.reviews || []) as AIReview[];
    }
  }

  return {
    run,
    decision,
    reviews,
    sourceSnapshot,
    exceptionId: exception?.id ?? null,
  };
}

function formatText(value: unknown) {
  if (value == null) return "-";
  const text = String(value).trim();
  return text.length ? text : "-";
}

function formatMoney(value: unknown) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return value.toFixed(2);
}

function formatConsistency(value: boolean | null | undefined) {
  if (value === true) {
    return { label: "pass", className: "bg-emerald-100 text-emerald-700" };
  }
  if (value === false) {
    return { label: "fail", className: "bg-rose-100 text-rose-700" };
  }
  return { label: "n/a", className: "bg-muted text-muted-foreground" };
}

function sourceErrorLabel(source: TransactionSourceData | undefined) {
  if (!source?.error) return "No details available.";
  if (source.error === "file_not_uploaded") return "No file uploaded for this source.";
  if (source.error === "merchant_ref_not_found") return "Merchant ref not found in this source file.";
  if (source.error.startsWith("file_parse_failed:")) return "Unable to parse this source file.";
  return source.error;
}

export default async function TransactionDetailPage(
  { params }: { params: Promise<{ id: string; merchantRef: string }> },
) {
  const { id, merchantRef: rawMerchantRef } = await params;
  const data = await getTransactionData(id, rawMerchantRef);

  if (!data.run) {
    return (
      <PageShell title="Transaction Trace">
        <p>Run not found.</p>
      </PageShell>
    );
  }

  if (!data.decision) {
    return (
      <PageShell title="Transaction Trace">
        <p className="mb-3 text-sm">Transaction not found for this run.</p>
        <Link href={`/runs/${id}`} className="rounded border px-3 py-2 text-sm">Back to Run</Link>
      </PageShell>
    );
  }

  const decision = data.decision;
  const reviews = data.reviews;
  const sourceSnapshot = data.sourceSnapshot;
  const exceptionId = data.exceptionId;
  const trace = (decision.trace_json || {}) as Record<string, unknown>;
  const exact = (trace.exact_hash || {}) as Record<string, unknown>;
  const fuzzy = (trace.fuzzy || {}) as Record<string, unknown>;
  const threeWay = (trace.three_way || {}) as Record<string, unknown>;
  const backdated = (trace.backdated || {}) as Record<string, unknown>;
  const fx = (trace.fx || {}) as Record<string, unknown>;
  const amountCheck = formatConsistency(sourceSnapshot?.checks?.amount_consistency);
  const identityCheck = formatConsistency(sourceSnapshot?.checks?.identity_consistency);

  return (
    <PageShell title={`Transaction ${decision.merchant_ref}`}>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Link href={`/runs/${id}`} className="rounded border px-3 py-2 text-sm">Back to Run</Link>
        <span className={`rounded-full px-2 py-1 text-xs ${decision.final_status === "good_transaction" ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
          {decision.final_status === "good_transaction" ? "good" : "doubtful"}
        </span>
      </div>

      <section className="mb-4 rounded-xl border bg-card p-4 text-xs">
        <h2 className="mb-2 font-medium">Summary</h2>
        <p className="text-muted-foreground">Run ID: <span className="font-mono">{id}</span></p>
        <p className="text-muted-foreground">Merchant Ref: <span className="font-mono">{decision.merchant_ref}</span></p>
        <p className="text-muted-foreground">Reason Codes: {decision.reason_codes.length ? decision.reason_codes.join(", ") : "-"}</p>
        <p className="text-muted-foreground">Fuzzy Score: {decision.fuzzy_score == null ? "n/a" : decision.fuzzy_score.toFixed(2)}</p>
      </section>

      <section className="mb-4 rounded-xl border bg-card p-4 text-xs">
        <h2 className="mb-2 font-medium">Source Values (Cashier vs Backoffice vs PSP)</h2>
        <p className="mb-3 text-muted-foreground">
          Key fields used for reconciliation are shown below so users can compare the three source records directly.
        </p>
        <div className="mb-3 flex flex-wrap gap-2">
          <span className="rounded-full border px-2 py-1">
            Compared Sources: {sourceSnapshot?.checks?.compared_sources ?? 0}/3
          </span>
          <span className={`rounded-full px-2 py-1 ${amountCheck.className}`}>
            Amount Consistency: {amountCheck.label}
          </span>
          <span className={`rounded-full px-2 py-1 ${identityCheck.className}`}>
            Identity Consistency: {identityCheck.label}
          </span>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          {SOURCE_ORDER.map((sourceKey) => {
            const source = sourceSnapshot?.sources?.[sourceKey];
            const row = source?.row;
            return (
              <article key={`${decision.merchant_ref}-${sourceKey}`} className="rounded-md border p-3">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <p className="font-medium">{SOURCE_LABELS[sourceKey]}</p>
                  <span className={`rounded-full px-2 py-1 ${source?.found ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
                    {source?.found ? "found" : "missing"}
                  </span>
                </div>
                <p className="mb-2 text-muted-foreground">File: {formatText(source?.filename)}</p>
                {source?.found && row ? (
                  <div className="grid grid-cols-2 gap-x-2 gap-y-1">
                    <span className="text-muted-foreground">Gross Amount</span><span>{formatMoney(row.gross_amount)}</span>
                    <span className="text-muted-foreground">Processing Fee</span><span>{formatMoney(row.processing_fee)}</span>
                    <span className="text-muted-foreground">Net Payout</span><span>{formatMoney(row.net_payout)}</span>
                    <span className="text-muted-foreground">Currency</span><span>{formatText(row.currency)}</span>
                    <span className="text-muted-foreground">Status</span><span>{formatText(row.status)}</span>
                    <span className="text-muted-foreground">Txn Date</span><span>{formatText(row.transaction_date)}</span>
                    <span className="text-muted-foreground">Settlement Date</span><span>{formatText(row.settlement_date)}</span>
                    <span className="text-muted-foreground">Client ID</span><span>{formatText(row.client_id)}</span>
                    <span className="text-muted-foreground">Client Name</span><span>{formatText(row.client_name)}</span>
                    <span className="text-muted-foreground">Payment Method</span><span>{formatText(row.payment_method)}</span>
                    <span className="text-muted-foreground">Bank Country</span><span>{formatText(row.bank_country)}</span>
                    <span className="text-muted-foreground">Settlement Bank</span><span>{formatText(row.settlement_bank)}</span>
                    <span className="text-muted-foreground">FX Rate</span><span>{formatText(row.fx_rate)}</span>
                    <span className="text-muted-foreground">Txn ID</span><span>{formatText(row.psp_txn_id)}</span>
                  </div>
                ) : (
                  <p className="text-muted-foreground">{sourceErrorLabel(source)}</p>
                )}
              </article>
            );
          })}
        </div>
      </section>

      <section className="mb-4 rounded-xl border bg-card p-4">
        <h2 className="mb-3 font-medium">Transaction Trace</h2>
        <div className="grid gap-3 text-xs md:grid-cols-2">
          <div className="rounded-md border p-3">
            <p className="font-medium">Trinity (3-Way) Check</p>
            <p className="mt-1 text-muted-foreground">Presence: {String(threeWay.presence_check ?? "n/a")}</p>
            <p className="text-muted-foreground">Amount consistency: {String(threeWay.amount_check ?? "n/a")}</p>
            <p className="text-muted-foreground">Identity consistency: {String(threeWay.identity_check ?? "n/a")}</p>
          </div>

          <div className="rounded-md border p-3">
            <p className="font-medium">Exact Hash</p>
            <p className="mt-1 text-muted-foreground">Matched: {String(exact.matched ?? decision.stage_results.exact_hash)}</p>
            <p className="text-muted-foreground">Hash samples: {JSON.stringify((exact.hashes || {}) as Record<string, unknown>)}</p>
          </div>

          <div className="rounded-md border p-3">
            <p className="font-medium">Fuzzy Logic</p>
            <p className="mt-1 text-muted-foreground">Score: {decision.fuzzy_score == null ? "n/a" : decision.fuzzy_score.toFixed(2)}</p>
            <p className="text-muted-foreground">Threshold: {String(fuzzy.threshold ?? "0.90")}</p>
            <p className="text-muted-foreground">Pair scores: {JSON.stringify((fuzzy.pair_scores || {}) as Record<string, unknown>)}</p>
          </div>

          <div className="rounded-md border p-3">
            <p className="font-medium">Backdated + FX</p>
            <p className="mt-1 text-muted-foreground">Backdated max gap: {decision.backdated_gap_days == null ? "n/a" : `${decision.backdated_gap_days} day(s)`}</p>
            <p className="text-muted-foreground">Gap details: {JSON.stringify((backdated.pair_gaps_days || {}) as Record<string, unknown>)}</p>
            <p className="text-muted-foreground">FX handling: {String(fx.detail ?? decision.fx_detail ?? "n/a")}</p>
          </div>
        </div>
      </section>

      <AITracePanel exceptionId={exceptionId} merchantRef={decision.merchant_ref} initialReviews={reviews} />
    </PageShell>
  );
}
