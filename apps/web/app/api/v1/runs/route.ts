import { NextRequest, NextResponse } from "next/server";

import { agno } from "@/lib/server-api";

export async function GET() {
  try {
    const payload = await agno("/v1/runs");
    return NextResponse.json(payload);
  } catch {
    return NextResponse.json({ runs: [] });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const run = await agno("/v1/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ initiated_by: body.initiatedBy || "analyst" }),
    });
    return NextResponse.json(run);
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}
