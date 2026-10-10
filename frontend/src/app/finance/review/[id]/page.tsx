"use client";

import { useParams } from "next/navigation";
import { ReviewView } from "@/components/ReviewView";

// Old link format, kept working; the app links to the static /finance/review/view?id= page
export default function Page() {
  const { id } = useParams<{ id: string }>();
  return <ReviewView id={id} />;
}
