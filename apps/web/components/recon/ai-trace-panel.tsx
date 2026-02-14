"use client";

import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import type { AIReview } from "@/lib/types";

type Props = {
  exceptionId?: string | null;
  merchantRef: string;
  initialReviews: AIReview[];
};

function formatText(value: unknown) {
  if (value == null) return "-";
  const text = String(value).trim();
  return text.length ? text : "-";
}

function formatTimestamp(value: unknown) {
  if (value == null) return "-";
  const raw = String(value).trim();
  if (!raw) return "-";
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return raw;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const day = String(parsed.getUTCDate()).padStart(2, "0");
  const month = months[parsed.getUTCMonth()] || "??";
  const year = String(parsed.getUTCFullYear());
  const hour = String(parsed.getUTCHours()).padStart(2, "0");
  const minute = String(parsed.getUTCMinutes()).padStart(2, "0");
  const second = String(parsed.getUTCSeconds()).padStart(2, "0");
  return `${day} ${month} ${year}, ${hour}:${minute}:${second} UTC`;
}

function stageTitle(stage: string) {
  if (stage === "intern") return "Intern Analysis";
  if (stage === "manager") return "Manager Review";
  if (stage === "supervisor") return "Supervisor Decision";
  return stage;
}

function formatBoolean(value: unknown) {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return "-";
}

export function AITracePanel({ exceptionId, merchantRef, initialReviews }: Props) {
  const router = useRouter();
  const [reviews, setReviews] = useState<AIReview[]>(initialReviews);
  const [error, setError] = useState("");
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    setReviews(initialReviews);
  }, [initialReviews]);

  function retriggerReview() {
    if (!exceptionId) {
      setError("This transaction has no exception record, so AI review cannot be retriggered.");
      return;
    }

    setError("");
    startTransition(() => {
      void (async () => {
        try {
          const response = await fetch(`/api/v1/exceptions/${encodeURIComponent(exceptionId)}/reviews`, { method: "POST" });
          const payload = await response.json().catch(() => ({ error: "Failed to retrigger AI review." }));
          if (!response.ok) {
            throw new Error(payload.error || "Failed to retrigger AI review.");
          }
          if (Array.isArray(payload.reviews)) {
            setReviews(payload.reviews as AIReview[]);
          }
          router.refresh();
        } catch (err) {
          setError((err as Error).message);
        }
      })();
    });
  }

  return (
    <section className="mb-4 rounded-xl border bg-card p-4 text-xs">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-medium">AI Handling Trace</h2>
        <button
          type="button"
          onClick={retriggerReview}
          disabled={isPending}
          className="rounded border px-2 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isPending ? "Rechecking..." : "Retrigger AI Review"}
        </button>
      </div>
      <p className="mb-3 text-muted-foreground">
        Re-run AI reasoning for <span className="font-mono">{merchantRef}</span> and refresh the latest review output.
      </p>
      {reviews.length === 0 ? <p className="text-muted-foreground">No AI exception review required/available for this transaction.</p> : null}
      <div className="space-y-2">
        {reviews.map((review, index) => (
          <div key={`${merchantRef}-${review.stage}-${index}`} className="rounded border p-2">
            <p className="font-medium">{stageTitle(review.stage)} ({Math.round(review.confidence * 100)}%)</p>
            <p className="mt-1 text-muted-foreground">
              Engine: {String(review.output_json?.engine || "unknown")}
              {review.output_json?.model ? ` • Model: ${String(review.output_json.model)}` : ""}
              {review.output_json?.reviewed_at ? ` • Reviewed: ${formatTimestamp(review.output_json.reviewed_at)}` : ""}
            </p>
            <p className="text-muted-foreground">
              Request: {String(review.output_json?.review_request_id || "-")}
            </p>
            <div className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1 text-muted-foreground">
              {review.stage === "intern" ? (
                <>
                  <span>Summary</span><span>{formatText(review.output_json?.summary)}</span>
                  <span>Root Cause</span><span>{formatText(review.output_json?.root_cause)}</span>
                </>
              ) : null}
              {review.stage === "manager" ? (
                <>
                  <span>Second Opinion</span><span>{formatText(review.output_json?.second_opinion)}</span>
                  <span>Agrees With Intern</span><span>{formatBoolean(review.output_json?.agreement_with_intern)}</span>
                </>
              ) : null}
              {review.stage === "supervisor" ? (
                <>
                  <span>Suggested Action</span><span>{formatText(review.output_json?.suggested_action)}</span>
                  <span>Note</span><span>{formatText(review.output_json?.note)}</span>
                </>
              ) : null}
            </div>
          </div>
        ))}
      </div>
      {error ? <p className="mt-2 text-rose-700">{error}</p> : null}
    </section>
  );
}
