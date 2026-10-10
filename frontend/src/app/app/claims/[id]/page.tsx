"use client";

import { useParams } from "next/navigation";
import { ClaimView } from "@/components/ClaimView";

// Old link format, kept working; the app links to the static /app/claims/view?id= page
export default function Page() {
  const { id } = useParams<{ id: string }>();
  return <ClaimView id={id} />;
}
