import { NextResponse } from "next/server";

import { agno } from "@/lib/server-api";

export async function GET(
  _: Request,
  { params }: { params: Promise<{ runId: string; merchantRef: string }> },
) {
  const { runId, merchantRef } = await params;
  try {
    const payload = await agno(`/v1/runs/${runId}/transactions/${encodeURIComponent(merchantRef)}`);
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 404 });
  }
}
