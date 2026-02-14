import { NextResponse } from "next/server";

import { agno } from "@/lib/server-api";

export async function POST(_: Request, { params }: { params: Promise<{ runId: string; month: string }> }) {
  const { runId, month } = await params;
  try {
    const payload = await agno(`/v1/runs/${runId}/monthly-submissions/${month}/notify`, {
      method: "POST",
    });
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}
