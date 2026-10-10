"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { ClaimView } from "@/components/ClaimView";
import { ErrorNote } from "@/components/ui";

function Inner() {
  const id = useSearchParams().get("id");
  return id ? <ClaimView key={id} id={id} /> : <ErrorNote error="No claim selected." />;
}

export default function Page() {
  return (
    <Suspense>
      <Inner />
    </Suspense>
  );
}
