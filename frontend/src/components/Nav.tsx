"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { setToken } from "@/lib/api";

export default function Nav() {
  const path = usePathname();
  const router = useRouter();
  return (
    <header className="nav">
      <Link href="/plan" className="brand">
        Day Planner
      </Link>
      <nav>
        <Link href="/plan" className={path === "/plan" ? "active" : ""}>
          Plan
        </Link>
        <Link href="/settings" className={path === "/settings" ? "active" : ""}>
          Settings
        </Link>
        <button
          className="link"
          onClick={() => {
            setToken(null);
            router.push("/login");
          }}
        >
          Log out
        </button>
      </nav>
    </header>
  );
}
