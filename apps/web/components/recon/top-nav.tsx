import Link from "next/link";

const links = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/daily-ops", label: "Daily Ops" },
  { href: "/monthly-close", label: "Monthly Close" },
  { href: "/runs/new", label: "New Run" },
  { href: "/inbox", label: "Inbox" },
  { href: "/settings/rules", label: "Rules" },
];

export function TopNav() {
  return (
    <header className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <Link href="/dashboard" className="font-semibold tracking-tight">
          Recon Finance
        </Link>
        <nav className="flex items-center gap-3 text-sm text-muted-foreground">
          {links.map((link) => (
            <Link key={link.href} href={link.href} className="rounded-md px-2 py-1 hover:bg-muted hover:text-foreground">
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
