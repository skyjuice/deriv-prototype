import { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  const runId = request.nextUrl.searchParams.get("runId") || "";
  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(`event: ready\ndata: ${JSON.stringify({ runId })}\n\n`));
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
