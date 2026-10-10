import Nav from "@/components/Nav";

export default function ModelLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Nav />
      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
      <footer className="mx-auto max-w-6xl px-4 pb-8 text-xs text-muted">
        Team Cognivex · AICON&apos;26 Build With AI · Trained on CORD v2 (CC-BY-4.0). Numbers come from the repo&apos;s results/ files.
      </footer>
    </>
  );
}
