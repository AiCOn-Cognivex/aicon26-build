import { AppShell } from "@/components/shell";

export default function FinanceLayout({ children }: { children: React.ReactNode }) {
  return <AppShell finance>{children}</AppShell>;
}
