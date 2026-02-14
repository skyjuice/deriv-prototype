import { DailyOpsBoard } from "@/components/recon/daily-ops-board";
import { PageShell } from "@/components/recon/page-shell";
import type { DailyOpsSummary } from "@/lib/types";

export const dynamic = "force-dynamic";

async function getDailyOps() {
  try {
    const response = await fetch(`${process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000"}/api/v1/daily-ops`, { cache: "no-store" });
    if (!response.ok) {
      return [];
    }
    const payload = await response.json();
    return (payload.items || []) as DailyOpsSummary[];
  } catch {
    return [] as DailyOpsSummary[];
  }
}

export default async function DailyOpsPage() {
  const items = await getDailyOps();
  return (
    <PageShell title="Daily Ops">
      <DailyOpsBoard items={items} />
    </PageShell>
  );
}
