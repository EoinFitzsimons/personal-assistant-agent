"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { setToken } from "@/lib/api";

const TABS = [
  { href: "/today", label: "Today" },
  { href: "/plan", label: "Week" },
  { href: "/promises", label: "Promises" },
  { href: "/goals", label: "Goals" },
  { href: "/review", label: "Review" },
];

export default function Nav() {
  const path = usePathname();
  const router = useRouter();
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <Link href="/today" className="brand">
          Day Planner
        </Link>
        <nav className="tabs" aria-label="Main">
          {TABS.map((t) => (
            <Link key={t.href} href={t.href} aria-current={path === t.href ? "page" : undefined}>
              {t.label}
            </Link>
          ))}
        </nav>
        <div className="topbar-end">
          <Link href="/settings" aria-current={path === "/settings" ? "page" : undefined}>
            Settings
          </Link>
          <button
            className="quiet"
            onClick={() => {
              setToken(null);
              router.push("/login");
            }}
          >
            Log out
          </button>
        </div>
      </div>
    </header>
  );
}
