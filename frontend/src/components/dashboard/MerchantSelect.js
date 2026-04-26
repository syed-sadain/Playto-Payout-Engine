import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { fetchMerchants } from "../../services/api";
import { ArrowRight, Zap } from "lucide-react";

export default function MerchantSelect() {
  const navigate = useNavigate();
  const { data: merchants, isLoading, error } = useQuery({
    queryKey: ["merchants"],
    queryFn: fetchMerchants,
    refetchInterval: false,
  });

  return (
    <div className="min-h-screen bg-[#050810] flex flex-col items-center justify-center px-4">
      {/* Grid background */}
      <div
        className="fixed inset-0 opacity-[0.03]"
        style={{
          backgroundImage:
            "linear-gradient(#3b82f6 1px, transparent 1px), linear-gradient(90deg, #3b82f6 1px, transparent 1px)",
          backgroundSize: "40px 40px",
        }}
      />

      <div className="relative z-10 w-full max-w-md">
        {/* Logo */}
        <div className="flex items-center gap-3 mb-12 justify-center">
          <div className="w-10 h-10 rounded-xl bg-blue-500 flex items-center justify-center">
            <Zap size={20} className="text-white" />
          </div>
          <div>
            <div className="text-white font-bold text-xl tracking-tight">Playto Pay</div>
            <div className="text-slate-500 text-xs font-mono">PAYOUT ENGINE</div>
          </div>
        </div>

        <div className="mb-6">
          <h1 className="text-2xl font-bold text-white text-center mb-2">Select Merchant</h1>
          <p className="text-slate-500 text-sm text-center font-mono">
            Choose a merchant to view their payout dashboard
          </p>
        </div>

        {isLoading && (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-20 rounded-xl bg-slate-900 animate-pulse" />
            ))}
          </div>
        )}

        {error && (
          <div className="bg-red-950/50 border border-red-800 rounded-xl p-4 text-red-400 text-sm font-mono text-center">
            Failed to load merchants. Is the backend running?
          </div>
        )}

        {merchants && (
          <div className="space-y-3">
            {merchants.map((m, idx) => (
              <button
                key={m.id}
                onClick={() => navigate(`/dashboard/${m.id}`)}
                className="w-full group flex items-center justify-between p-5 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-blue-500/50 hover:bg-slate-800/80 transition-all duration-200"
              >
                <div className="flex items-center gap-4">
                  <div
                    className="w-10 h-10 rounded-lg flex items-center justify-center text-sm font-bold"
                    style={{
                      background: ["#1d4ed8", "#7c3aed", "#0f766e"][idx % 3],
                    }}
                  >
                    {m.name.charAt(0)}
                  </div>
                  <div className="text-left">
                    <div className="text-white font-semibold text-sm">{m.name}</div>
                    <div className="text-slate-500 text-xs font-mono">{m.email}</div>
                  </div>
                </div>
                <ArrowRight
                  size={16}
                  className="text-slate-600 group-hover:text-blue-400 transition-colors"
                />
              </button>
            ))}
          </div>
        )}

        <div className="mt-8 text-center text-slate-600 text-xs font-mono">
          PLAYTO PAYOUT ENGINE v1.0 · PRODUCTION BUILD
        </div>
      </div>
    </div>
  );
}
