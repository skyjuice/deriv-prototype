import { PageShell } from "@/components/recon/page-shell";
import type { Announcement } from "@/lib/types";
import { RiCheckboxCircleFill, RiNotification3Line } from "@remixicon/react";

export const dynamic = "force-dynamic";

async function getInbox() {
  const response = await fetch(`${process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000"}/api/v1/inbox`, { cache: "no-store" });
  if (!response.ok) {
    return { items: [] };
  }
  return response.json() as Promise<{ items: Announcement[] }>;
}

export default async function InboxPage() {
  const data = await getInbox();

  return (
    <PageShell title="AI Inbox">
      <div className="space-y-3">
        {data.items?.length === 0 ? <p className="text-sm text-muted-foreground">No announcements yet.</p> : null}
        {(data.items || []).map((item) => (
          <article key={item.id} className="rounded-xl border bg-card p-4">
            <div className="flex items-center justify-between">
              <h2 className="font-medium">{item.title}</h2>
              <div className="flex items-center gap-2">
                <span className="rounded-full bg-muted px-2 py-0.5 text-xs uppercase">{item.level}</span>
                {item.level === "good" ? (
                  <span className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-2 py-1 text-xs font-medium text-white">
                    <RiCheckboxCircleFill size={14} />
                    Success
                    <RiNotification3Line size={14} />
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-xs font-medium text-amber-700">
                    <RiNotification3Line size={14} />
                    Attention
                  </span>
                )}
              </div>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">{item.message}</p>
          </article>
        ))}
      </div>
    </PageShell>
  );
}
