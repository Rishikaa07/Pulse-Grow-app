"use client";

import { SessionProvider } from "@/lib/session";

/** Everything behind the sign-in wall shares one session context. */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <SessionProvider>{children}</SessionProvider>;
}
