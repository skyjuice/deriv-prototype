"use client";

import { useState } from "react";

import { PageShell } from "@/components/recon/page-shell";

const SOURCES = ["internal", "erp", "psp"] as const;
type SourceType = (typeof SOURCES)[number];
const SOURCE_LABELS: Record<SourceType, string> = {
  internal: "Internal",
  erp: "Backoffice",
  psp: "PSP",
};

export default function NewRunPage() {
  const [runId, setRunId] = useState<string>("");
  const [files, setFiles] = useState<Partial<Record<SourceType, File>>>({});
  const [urlSource, setUrlSource] = useState<SourceType>("psp");
  const [url, setUrl] = useState("");
  const [status, setStatus] = useState("");

  const ensureRun = async () => {
    if (runId) {
      return runId;
    }
    const response = await fetch("/api/v1/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ initiatedBy: "analyst" }),
    });
    const payload = await response.json();
    setRunId(payload.id);
    return payload.id as string;
  };

  const upload = async (currentRun: string, sourceType: SourceType) => {
    const file = files[sourceType];
    if (!file) {
      throw new Error(`Missing required file: ${SOURCE_LABELS[sourceType]}`);
    }

    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch(`/api/v1/runs/${currentRun}/files?sourceType=${sourceType}`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      throw new Error(`Failed upload for ${SOURCE_LABELS[sourceType]}`);
    }
  };

  const uploadAllAndStart = async () => {
    try {
      const missing = SOURCES.filter((source) => !files[source]);
      if (missing.length > 0) {
        setStatus(`Missing required file(s): ${missing.map((source) => SOURCE_LABELS[source]).join(", ")}`);
        return;
      }

      const currentRun = await ensureRun();
      setStatus("Uploading files...");
      await Promise.all(SOURCES.map((source) => upload(currentRun, source)));
      setStatus("Starting reconciliation...");
      const response = await fetch(`/api/v1/runs/${currentRun}/start`, { method: "POST" });
      if (!response.ok) {
        throw new Error("Failed to start run");
      }
      setStatus(`Run started: ${currentRun}`);
    } catch (error) {
      setStatus((error as Error).message);
    }
  };

  const fetchRemote = async () => {
    const currentRun = await ensureRun();
    const response = await fetch(`/api/v1/runs/${currentRun}/fetch-remote`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sourceType: urlSource, url }),
    });
    const payload = await response.json();
    if (!response.ok) {
      setStatus(payload.error || "Failed remote fetch");
      return;
    }
    setStatus(`Remote file attached for ${SOURCE_LABELS[urlSource]}`);
  };

  return (
    <PageShell title="New Reconciliation Run">
      <section className="grid gap-4 lg:grid-cols-2">
        <article className="rounded-xl border bg-card p-4">
          <h2 className="font-medium">Manual upload (required)</h2>
          <p className="mb-4 text-sm text-muted-foreground">Attach Internal, Backoffice, and PSP files.</p>
          <div className="space-y-3">
            {SOURCES.map((source) => (
              <label key={source} className="block rounded-lg border p-3 text-sm">
                <span className="mb-2 block">{SOURCE_LABELS[source]}</span>
                <input type="file" onChange={(event) => setFiles((prev) => ({ ...prev, [source]: event.target.files?.[0] }))} />
              </label>
            ))}
          </div>
          <button onClick={uploadAllAndStart} className="mt-4 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground">
            Upload and Start
          </button>
        </article>

        <article className="rounded-xl border bg-card p-4">
          <h2 className="font-medium">AI URL Pull</h2>
          <p className="mb-4 text-sm text-muted-foreground">Fetch a remote statement and attach it to the run.</p>
          <div className="space-y-3">
            <select className="w-full rounded-lg border px-3 py-2 text-sm" value={urlSource} onChange={(e) => setUrlSource(e.target.value as SourceType)}>
              {SOURCES.map((source) => (
                <option value={source} key={source}>{SOURCE_LABELS[source]}</option>
              ))}
            </select>
            <input value={url} onChange={(e) => setUrl(e.target.value)} className="w-full rounded-lg border px-3 py-2 text-sm" placeholder="https://example.com/statement.csv" />
            <button onClick={fetchRemote} className="rounded-lg border px-3 py-2 text-sm">Attach Remote File</button>
          </div>
        </article>
      </section>

      {runId ? <p className="mt-4 text-sm text-muted-foreground">Run ID: <span className="font-mono">{runId}</span></p> : null}
      {status ? <p className="mt-2 text-sm">{status}</p> : null}
    </PageShell>
  );
}
