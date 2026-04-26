import React, { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchMerchant } from "../../services/api";
import BalanceCard from "./BalanceCard";
import PayoutForm from "../payouts/PayoutForm";
import PayoutTable from "../payouts/PayoutTable";
import LedgerTable from "./LedgerTable";
import { ArrowLeft, Zap, RefreshCw } from "lucide-react";

export default function Dashboard() {
  const { merchantId } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState("payouts");

  const { data: merchant, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["merchant", merchantId],
    queryFn: () => fetchMerchant(merchantId),
    refetchInterval: 5000,
  });

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#050810] flex items-center justify-center">
        <div className="flex items-center gap-3 text-slate-400 font-mono text-sm">
          <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          Loading merchant data...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[#050810] flex items-center justify-center">
        <div className="bg-red-950/50 border border-red-800 rounded-xl p-6 text-center max-w-sm">
          <div className="text-red-400 font-mono text-sm">Failed to load merchant.</div>
          <button
            onClick={() => navigate("/")}
            className="mt-4 text-blue-400 text-xs font-mono hover:underline"
          >
            ← Go back
          </button>
        </div>
      </div>
    );
  }

  const tabs = [
    { id: "payouts", label: "Payouts" },
    { id: "ledger", label: "Ledger" },
  ];

  return (
    <div className="min-h-screen bg-[#050810]">
      {/* Grid bg */}
      <div
        className="fixed inset-0 opacity-[0.025]"
        style={{
          backgroundImage:
            "linear-gradient(#3b82f6 1px, transparent 1px), linear-gradient(90deg, #3b82f6 1px, transparent 1px)",
          backgroundSize: "40px 40px",
        }}
      />

      {/* Header */}
      <header className="relative z-10 border-b border-slate-800/80 bg-[#050810]/90 backdrop-blur-sm sticky top-0">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate("/")}
              className="text-slate-500 hover:text-white transition-colors"
            >
              <ArrowLeft size={18} />
            </button>
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-md bg-blue-500 flex items-center justify-center">
                <Zap size={13} className="text-white" />
              </div>
              <span className="text-white font-semibold text-sm">{merchant.name}</span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-slate-500 text-xs font-mono hidden sm:block">
              {merchant.email}
            </span>
            <button
              onClick={refetch}
              className="text-slate-500 hover:text-white transition-colors"
            >
              <RefreshCw size={14} className={isFetching ? "animate-spin" : ""} />
            </button>
          </div>
        </div>
      </header>

      <main className="relative z-10 max-w-7xl mx-auto px-4 py-8">
        {/* Balance cards */}
        <BalanceCard balance={merchant.balance} />

        {/* Payout form */}
        <div className="mt-8 mb-8">
          <PayoutForm merchant={merchant} />
        </div>

        {/* Tabs */}
        <div className="border-b border-slate-800 mb-6 flex gap-6">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`pb-3 text-sm font-mono transition-colors relative ${
                activeTab === tab.id
                  ? "text-blue-400"
                  : "text-slate-500 hover:text-slate-300"
              }`}
            >
              {tab.label}
              {activeTab === tab.id && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-500 rounded-t" />
              )}
            </button>
          ))}
        </div>

        {activeTab === "payouts" && <PayoutTable merchantId={merchantId} />}
        {activeTab === "ledger" && <LedgerTable merchantId={merchantId} />}
      </main>
    </div>
  );
}
