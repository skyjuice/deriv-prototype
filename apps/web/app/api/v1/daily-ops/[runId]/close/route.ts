import { NextResponse } from "next/server";

import { agno } from "@/lib/server-api";

export async function POST(_: Request, { params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  try {
    const payload = await agno(`/v1/daily-ops/${runId}/close`, { method: "POST" });
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}
