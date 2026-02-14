import { ChatWidget } from "@/components/recon/chat-widget";
import { TopNav } from "@/components/recon/top-nav";

export function PageShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gradient-to-b from-background via-background to-muted/40">
      <TopNav />
      <main className="mx-auto max-w-6xl px-4 py-8">
        <h1 className="mb-6 text-2xl font-semibold tracking-tight">{title}</h1>
        {children}
      </main>
      <ChatWidget />
    </div>
  );
}
