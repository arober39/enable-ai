import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Agent Architect",
  description:
    "Figure out what agent to build from the work you actually do, then supervise it.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-paper text-ink antialiased">
        <div className="mx-auto max-w-4xl px-6 py-10">
          <nav className="mb-8 flex items-center gap-4 border-b border-neutral-200 pb-4 text-sm">
            <a href="/" className="font-semibold text-ink hover:text-accent">
              Agent Architect
            </a>
            <span className="text-neutral-400">/</span>
            <a href="/settings" className="text-neutral-600 hover:text-accent">
              Settings
            </a>
          </nav>
          {children}
        </div>
      </body>
    </html>
  );
}
