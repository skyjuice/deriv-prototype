import Link from "next/link";

export default function LoginPage() {
  return (
    <main className="grid min-h-screen place-items-center bg-gradient-to-br from-orange-100/60 via-background to-zinc-100/60 p-4">
      <section className="w-full max-w-md rounded-2xl border bg-card p-6 shadow-sm">
        <h1 className="text-xl font-semibold">Sign in</h1>
        <p className="mt-1 text-sm text-muted-foreground">PocketBase auth is wired at backend level for phase 1.</p>
        <div className="mt-6 space-y-3">
          <input className="w-full rounded-lg border px-3 py-2 text-sm" placeholder="Email" />
          <input className="w-full rounded-lg border px-3 py-2 text-sm" placeholder="Password" type="password" />
          <button className="w-full rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground">Login</button>
        </div>
        <Link href="/dashboard" className="mt-4 block text-center text-sm text-muted-foreground underline">
          Continue to dashboard (dev)
        </Link>
      </section>
    </main>
  );
}
