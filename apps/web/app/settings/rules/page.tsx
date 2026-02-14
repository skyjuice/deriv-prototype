import { PageShell } from "@/components/recon/page-shell";

export default function RulesPage() {
  return (
    <PageShell title="Rules (Admin)">
      <div className="rounded-xl border bg-card p-4">
        <p className="font-medium">Phase 1 defaults (read-only)</p>
        <ul className="mt-3 space-y-1 text-sm text-muted-foreground">
          <li>Fuzzy threshold: 0.90</li>
          <li>Backdated window: 3 days</li>
          <li>Status normalization: captured|confirmed|settled =&gt; SUCCESS</li>
          <li>3-way validation: presence + amount + client/currency/bank consistency</li>
        </ul>
      </div>
    </PageShell>
  );
}
