import { AppShell } from "@/components/shell";

export default function EmployeeLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
