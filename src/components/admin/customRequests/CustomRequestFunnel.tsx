"use client";

import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { Alert } from "@/components/feedback/Alert";
import { TextField } from "@/components/forms/TextField";
import { describeAdminError } from "@/lib/admin/adminErrorMessages";
import {
  customRequestKeys,
  customRequestsAdminApi,
  type CustomRequestFunnelDTO,
  type CustomRequestFunnelParams,
} from "@/lib/admin/customRequests/customRequestsAdminApi";
import { dayEndExclusive, dayStart } from "@/lib/admin/dateRange";
import type { ApiError } from "@/lib/api/ApiError";
import { formatOrderDate } from "@/lib/orders/orderFormat";

// #FVS-BYI-FUNNEL (phase 6B-2) — GET /admin/analytics/custom-requests/funnel.
// Shows exactly the server's numbers for one submission-date cohort; no
// derived rates, charts or extra analytics. A stage counts every lead that
// ever reached it (a lost quote still counts as quoted). Blank dates mean
// the server default (the last 90 days); the span is at most 366 days.

const RANGE_ERROR = "Choose a range of at most 366 days, with the end after the start.";

function Stat({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0 rounded-card border border-outline-variant/40 bg-surface-container-lowest p-4 shadow-sm tablet:p-5">
      <dt className="font-label text-label-sm uppercase text-on-surface-variant">{label}</dt>
      <dd className="mt-2 break-words font-headline text-headline-md text-on-surface tablet:text-headline-lg">
        {children}
      </dd>
    </div>
  );
}

export function CustomRequestFunnel() {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const params: CustomRequestFunnelParams = {
    ...(dayStart(from) ? { from: dayStart(from) } : {}),
    ...(dayEndExclusive(to) ? { to: dayEndExclusive(to) } : {}),
  };
  const funnel = useQuery<CustomRequestFunnelDTO, ApiError>({
    queryKey: customRequestKeys.funnel(params),
    queryFn: () => customRequestsAdminApi.getFunnel(params),
  });
  const data = funnel.data;
  // The server's `to` is exclusive: show the last included day.
  const lastDay = data ? formatOrderDate(new Date(new Date(data.to).getTime() - 1).toISOString()) : "";

  return (
    <section
      aria-labelledby="byi-funnel"
      className="mt-6 rounded-card border border-outline-variant/40 bg-surface-container-low p-4 tablet:p-6"
    >
      <h2 id="byi-funnel" className="font-headline text-headline-md text-on-surface">
        Funnel
      </h2>
      <p className="mt-1 max-w-3xl font-body text-body-md text-on-surface-variant">
        Requests submitted in the range, and how far they got. A stage counts every request that ever reached it.
      </p>
      <div className="mt-4 grid gap-4 tablet:grid-cols-2">
        <TextField
          label="Submitted from"
          type="date"
          value={from}
          onChange={(e) => setFrom(e.target.value)}
          hint="Blank: the last 90 days."
        />
        <TextField label="Submitted to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
      </div>
      {funnel.isError && (
        <div className="mt-3">
          <Alert
            variant="error"
            message={
              funnel.error?.kind === "http" && funnel.error.status === 422
                ? RANGE_ERROR
                : describeAdminError(funnel.error)
            }
          />
        </div>
      )}
      {data && (
        <>
          <p className="mt-4 font-label text-label-sm uppercase text-on-surface-variant">
            {formatOrderDate(data.from)} – {lastDay}
          </p>
          <dl className="mt-3 grid grid-cols-2 gap-3 tablet:grid-cols-4">
            <Stat label="Submitted">{data.submitted}</Stat>
            <Stat label="Contacted">{data.contacted}</Stat>
            <Stat label="Quoted">{data.quoted}</Stat>
            <Stat label="Won">{data.won}</Stat>
            <Stat label="Lost">{data.lost}</Stat>
            <Stat label="Open">{data.open}</Stat>
            <Stat label="Quoted total">
              <PriceDisplay amountCents={data.quoted_total_cents} currency={data.currency} />
            </Stat>
            <Stat label="Won total">
              <PriceDisplay amountCents={data.won_total_cents} currency={data.currency} />
            </Stat>
          </dl>
        </>
      )}
    </section>
  );
}
