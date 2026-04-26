import React from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchLedger } from "../../services/api";
import { format } from "date-fns";
import { ArrowDownLeft, ArrowUpRight } from "lucide-react";

export default function LedgerTable({ merchantId }) {
  const { data, isLoading } = useQuery({
    queryKey: ["ledger", merchantId],
    queryFn: () => fetchLedger(merchantId),
    refetchInterval: 5000,
  });

  if (isLoading) return <TableSkeleton />;

  const entries = data?.results ?? [];

  return (
    <div className="rounded-xl border border-slate-800 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-800 bg-slate-900/50">
              {["Type", "Amount", "Description", "Date"].map((h) => (
                <th
                  key={h}
                  className="text-left px-4 py-3 text-slate-500 font-mono text-xs uppercase tracking-wider"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entries.length === 0 ? (
              <tr>
                <td colSpan={4} className="text-center py-12 text-slate-600 font-mono text-xs">
                  No ledger entries yet.
                </td>
              </tr>
            ) : (
              entries.map((entry) => (
                <tr
                  key={entry.id}
                  className="border-b border-slate-800/50 hover:bg-slate-900/50 transition-colors"
                >
                  <td className="px-4 py-3">
                    {entry.entry_type === "CREDIT" ? (
                      <span className="flex items-center gap-1.5 text-emerald-400 font-mono text-xs">
                        <ArrowDownLeft size={13} />
                        CREDIT
                      </span>
                    ) : (
                      <span className="flex items-center gap-1.5 text-red-400 font-mono text-xs">
                        <ArrowUpRight size={13} />
                        DEBIT
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`font-mono font-semibold ${
                        entry.entry_type === "CREDIT" ? "text-emerald-300" : "text-red-300"
                      }`}
                    >
                      {entry.entry_type === "CREDIT" ? "+" : "-"}
                      {entry.amount_inr}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-xs max-w-xs truncate">
                    {entry.description}
                  </td>
                  <td className="px-4 py-3 text-slate-500 font-mono text-xs">
                    {format(new Date(entry.created_at), "dd MMM yy · HH:mm")}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="rounded-xl border border-slate-800 overflow-hidden">
      {[...Array(5)].map((_, i) => (
        <div key={i} className="h-12 border-b border-slate-800 bg-slate-900 animate-pulse" />
      ))}
    </div>
  );
}
