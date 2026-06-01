import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Enable AI — test UI",
  description:
    "Pick a support stack, get an EnablementPlan from the Support Enablement Agent.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-paper text-ink antialiased">
        <div className="mx-auto max-w-4xl px-6 py-10">{children}</div>
      </body>
    </html>
  );
}
