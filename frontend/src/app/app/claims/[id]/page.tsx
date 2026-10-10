"use client";

import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { ClaimImage, ClaimSummary, Reasons, Timeline } from "@/components/claimDetail";
import { PageHeader, PageLoader } from "@/components/shell";
import { Card, ErrorNote, LinkButton } from "@/components/ui";
import type { ClaimFull } from "@/lib/appTypes";
import { useApi } from "@/lib/useApi";

export default function ClaimPage() {
  const { id } = useParams<{ id: string }>();
  const { data: c, error, reload } = useApi<ClaimFull>(`/claims/${id}`);
  return (
    <>
      <PageHeader
        title={c ? c.merchant || c.wallet?.name || "Claim" : "Claim"}
        sub={c ? `${c.wallet?.name} claim` : undefined}
        actions={
          <LinkButton href="/app/claims" variant="soft" size="sm">
            <ArrowLeft size={15} /> All claims
          </LinkButton>
        }
      />
      {error && <ErrorNote error={error} onRetry={reload} />}
      {!c && !error && <PageLoader label="Loading claim…" />}
      {c && (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
          <div className="animate-fade-up">
            <ClaimImage c={c} />
          </div>
          <div className="space-y-5 animate-fade-up [animation-delay:60ms]">
            <ClaimSummary c={c} />
            <Reasons c={c} />
            <Card className="p-6">
              <p className="mb-4 text-[15px] font-semibold">Timeline</p>
              <Timeline events={c.timeline ?? []} />
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
