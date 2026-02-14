import { NextRequest, NextResponse } from "next/server";

import { agno } from "@/lib/server-api";

export async function POST(request: NextRequest, { params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const body = await request.json();
  try {
    const payload = await agno(`/v1/daily-ops/${runId}/business-date`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ business_date: body.businessDate }),
    });
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}
