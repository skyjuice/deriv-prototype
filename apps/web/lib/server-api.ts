const AGNO_API_URL = process.env.AGNO_API_URL || "http://localhost:8001";

export async function agno(path: string, init?: RequestInit) {
  const response = await fetch(`${AGNO_API_URL}${path}`, {
    ...init,
    cache: "no-store",
  });

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : { message: await response.text() };

  if (!response.ok) {
    throw new Error(payload.detail || payload.message || "Upstream request failed");
  }

  return payload;
}
