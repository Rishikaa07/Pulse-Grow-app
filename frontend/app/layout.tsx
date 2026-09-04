import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Pulse — Know what changed",
  description:
    "A market attention engine. Ranks your watchlist by what actually deserves your attention, and shows the arithmetic behind every call.",
};

export const viewport: Viewport = {
  themeColor: "#06070A",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-dvh font-sans antialiased">
        <a
          href="#main"
          className="sr-only-focusable fixed left-4 top-4 z-[100] rounded bg-accent px-3 py-2 text-sm font-medium text-void"
        >
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
