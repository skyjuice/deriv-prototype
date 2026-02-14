import { NextResponse } from "next/server";

import { agno } from "@/lib/server-api";

export async function GET() {
  try {
    const payload = await agno("/v1/inbox");
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}
