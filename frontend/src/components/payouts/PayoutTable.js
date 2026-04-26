import React from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchPayouts } from "../../services/api";
import { format } from "date-fns";
import { Clock, CheckCircle, XCircle, Loader, RefreshCw } from "lucide-react";

const STATUS_CONFIG = {
  PENDING: {
    label: "Pending",
    icon: Clock,
    className: "text-amber-400 bg-amber-500/10 border-amber-500/20",
    dot: "bg-amber-400",
  },
  PROCESSING: {
    label: "Processing",
    icon: Loader,
    className: "text-blue-400 bg-blue-500/10 border-blue-500/20",
    dot: "bg-blue-400 animate-pulse",
    spin: true,
  },
  COMPLETED: {
    label: "Completed",
    icon: CheckCircle,
    className: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
    dot: "bg-emerald-400",
  },
  FAILED: {
    label: "Failed",
    icon: XCircle,
    className: "text-red-400 bg-red-500/10 border-red-500/20",
    dot: "bg-red-400",
  },
};

function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.PENDING;
  const Icon = cfg.icon;
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-mono ${cfg.className}`}
    >
      <Icon size={11} className={cfg.spin ? "animate-spin" : ""} />
      {cfg.label}
    </span>
  );
}

function fmt(paise) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 2,
  }).format(paise / 100);
}

export default function PayoutTable({ merchantId }) {
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["payouts", merchantId],
    queryFn: () => fetchPayouts(merchantId),
    refetchInterval: 3000, // Live status updates every 3s
  });

  const payouts = data?.results ?? [];
  const liveCount = payouts.filter(
    (p) => p.status === "PENDING" || p.status === "PROCESSING"
  ).length;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h3 className="text-white font-semibold text-sm">Payout History</h3>
          {liveCount > 0 && (
            <span className="flex items-center gap-1.5 text-blue-400 text-xs font-mono bg-blue-500/10 border border-blue-500/20 px-2 py-0.5 rounded-full">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
              {liveCount} live
            </span>
          )}
        </div>
        <button
          onClick={refetch}
          className="text-slate-500 hover:text-white transition-colors"
        >
          <RefreshCw size={13} className={isFetching ? "animate-spin" : ""} />
        </button>
      </div>

      <div className="rounded-xl border border-slate-800 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-900/60">
                {["Payout ID", "Amount", "Status", "Bank Account", "Attempts", "Created"].map(
                  (h) => (
                    <th
                      key={h}
                      className="text-left px-4 py-3 text-slate-500 font-mono text-xs uppercase tracking-wider whitespace-nowrap"
                    >
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                [...Array(5)].map((_, i) => (
                  <tr key={i} className="border-b border-slate-800/50">
                    {[...Array(6)].map((_, j) => (
                      <td key={j} className="px-4 py-3">
                        <div className="h-4 bg-slate-800 rounded animate-pulse" />
                      </td>
                    ))}
                  </tr>
                ))
              ) : payouts.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className="text-center py-16 text-slate-600 font-mono text-xs"
                  >
                    No payouts yet. Create one above.
                  </td>
                </tr>
              ) : (
                payouts.map((payout) => (
                  <PayoutRow key={payout.id} payout={payout} />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function PayoutRow({ payout }) {
  const isLive =
    payout.status === "PENDING" || payout.status === "PROCESSING";

  return (
    <tr
      className={`border-b border-slate-800/50 transition-colors ${
        isLive ? "bg-slate-900/30" : "hover:bg-slate-900/30"
      }`}
    >
      {/* ID */}
      <td className="px-4 py-3">
        <span className="font-mono text-xs text-slate-400" title={payout.id}>
          {payout.id.slice(0, 8)}…
        </span>
      </td>

      {/* Amount */}
      <td className="px-4 py-3">
        <span className="font-mono font-semibold text-white">
          {fmt(payout.amount_paise)}
        </span>
      </td>

      {/* Status */}
      <td className="px-4 py-3">
        <StatusBadge status={payout.status} />
        {payout.failure_reason && (
          <div className="text-red-500 text-xs font-mono mt-1 max-w-[180px] truncate" title={payout.failure_reason}>
            {payout.failure_reason}
          </div>
        )}
      </td>

      {/* Bank account */}
      <td className="px-4 py-3">
        <div className="text-slate-300 text-xs">{payout.bank_account?.bank_name}</div>
        <div className="text-slate-600 font-mono text-xs">
          {payout.bank_account?.masked_account}
        </div>
      </td>

      {/* Attempts */}
      <td className="px-4 py-3">
        <span
          className={`font-mono text-xs ${
            payout.attempt_count >= 3
              ? "text-red-400"
              : payout.attempt_count >= 2
              ? "text-amber-400"
              : "text-slate-500"
          }`}
        >
          {payout.attempt_count} / 3
        </span>
      </td>

      {/* Created */}
      <td className="px-4 py-3 text-slate-500 font-mono text-xs whitespace-nowrap">
        {format(new Date(payout.created_at), "dd MMM · HH:mm:ss")}
      </td>
    </tr>
  );
}
