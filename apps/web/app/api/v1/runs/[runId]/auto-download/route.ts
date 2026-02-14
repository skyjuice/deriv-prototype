import { NextRequest, NextResponse } from "next/server";

import { agno } from "@/lib/server-api";

export async function POST(request: NextRequest, { params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;

  let sourceType = "psp";
  let task: string | undefined;

  try {
    const body = (await request.json()) as { sourceType?: string; task?: string };
    sourceType = (body.sourceType || "psp").toLowerCase();
    task = body.task?.trim() || undefined;
  } catch {
    sourceType = "psp";
  }

  if (!["internal", "erp", "psp"].includes(sourceType)) {
    return NextResponse.json({ error: "sourceType must be internal, erp, or psp" }, { status: 400 });
  }

  try {
    const payload = await agno(`/v1/runs/${runId}/auto-download`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_type: sourceType, task }),
    });
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}
