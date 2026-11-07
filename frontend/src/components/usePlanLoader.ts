"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getToken, Plan } from "@/lib/api";

export function usePlanLoader(load: () => Promise<Plan | null>) {
  const router = useRouter();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    load()
      .then((p) => setPlan(p))
      .catch((e) => setError(e.message))
      .finally(() => setLoaded(true));
  }, [router, load]);

  return { plan, setPlan, loaded, error, setError };
}
