import { MonthlyCloseBoard } from "@/components/recon/monthly-close-board";
import { PageShell } from "@/components/recon/page-shell";
import type { MonthlyCloseBatch } from "@/lib/types";

export const dynamic = "force-dynamic";

async function getMonthlyClose() {
  try {
    const response = await fetch(`${process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000"}/api/v1/monthly-close`, { cache: "no-store" });
    if (!response.ok) {
      return [];
    }
    const payload = await response.json();
    return (payload.items || []) as MonthlyCloseBatch[];
  } catch {
    return [] as MonthlyCloseBatch[];
  }
}

export default async function MonthlyClosePage() {
  const items = await getMonthlyClose();
  return (
    <PageShell title="Monthly Close">
      <MonthlyCloseBoard items={items} />
    </PageShell>
  );
}
