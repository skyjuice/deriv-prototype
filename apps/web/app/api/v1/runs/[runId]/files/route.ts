import { NextResponse } from "next/server";

import { agno } from "@/lib/server-api";

export async function POST(request: Request, { params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const url = new URL(request.url);
  const sourceType = url.searchParams.get("sourceType");
  if (!sourceType) {
    return NextResponse.json({ error: "sourceType is required" }, { status: 400 });
  }

  const incoming = await request.formData();
  const file = incoming.get("file") as File | null;
  if (!file) {
    return NextResponse.json({ error: "file is required" }, { status: 400 });
  }

  const formData = new FormData();
  formData.append("file", file, file.name);

  try {
    const payload = await agno(`/v1/runs/${runId}/files?source_type=${sourceType}`, {
      method: "POST",
      body: formData,
    });
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}
