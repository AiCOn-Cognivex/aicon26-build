"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { ReviewView } from "@/components/ReviewView";
import { ErrorNote } from "@/components/ui";

function Inner() {
  const id = useSearchParams().get("id");
  // key: moving to the next claim in the queue starts with a fresh form
  return id ? <ReviewView key={id} id={id} /> : <ErrorNote error="No claim selected." />;
}

export default function Page() {
  return (
    <Suspense>
      <Inner />
    </Suspense>
  );
}
