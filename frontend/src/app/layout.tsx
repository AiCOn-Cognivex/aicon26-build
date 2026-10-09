import type { Metadata } from "next";
import "./globals.css";
import Nav from "@/components/Nav";

export const metadata: Metadata = {
  title: "Cognivex · Receipt Auto-Post",
  description: "Receipt extraction with a calibrated AUTO-POST vs HUMAN REVIEW decision (AICON'26, Team Cognivex).",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <Nav />
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
        <footer className="mx-auto max-w-6xl px-4 pb-8 text-xs text-muted">
          Team Cognivex · AICON&apos;26 Build With AI · Trained on CORD v2 (CC-BY-4.0). Numbers come from the repo&apos;s results/ files.
        </footer>
      </body>
    </html>
  );
}
