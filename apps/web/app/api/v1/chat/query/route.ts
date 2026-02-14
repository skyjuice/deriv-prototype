import { NextResponse } from "next/server";

import { agno } from "@/lib/server-api";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const payload = await agno("/v1/chat/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}
