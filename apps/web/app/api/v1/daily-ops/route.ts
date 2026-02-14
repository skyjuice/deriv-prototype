import { NextResponse } from "next/server";

import { agno } from "@/lib/server-api";

export async function GET() {
  try {
    const payload = await agno("/v1/daily-ops");
    return NextResponse.json(payload);
  } catch {
    return NextResponse.json({ items: [] });
  }
}
