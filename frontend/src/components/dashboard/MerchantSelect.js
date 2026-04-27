import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { fetchMerchants } from "../../services/api";
import { ArrowRight, Zap } from "lucide-react";

export default function MerchantSelect() {
  const navigate = useNavigate();

  const { data, isLoading, error } = useQuery({
    queryKey: ["merchants"],
    queryFn: fetchMerchants,
    refetchInterval: false,
  });

  // ✅ Normalize data (IMPORTANT FIX)
  const merchants = data?.results || data || [];

  return (
    <div className="min-h-screen bg-[#050810] flex flex-col items-center justify-center px-4">
      
      <div className="relative z-10 w-full max-w-md">
        
        {/* Header */}
        <div className="flex items-center gap-3 mb-12 justify-center">
          <div className="w-10 h-10 rounded-xl bg-blue-500 flex items-center justify-center">
            <Zap size={20} className="text-white" />
          </div>
          <div>
            <div className="text-white font-bold text-xl">Playto Pay</div>
            <div className="text-slate-500 text-xs font-mono">PAYOUT ENGINE</div>
          </div>
        </div>

        {/* Title */}
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-bold text-white mb-2">Select Merchant</h1>
          <p className="text-slate-500 text-sm font-mono">
            Choose a merchant to view their payout dashboard
          </p>
        </div>

        {/* Loading */}
        {isLoading && (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-20 rounded-xl bg-slate-900 animate-pulse" />
            ))}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="bg-red-950/50 border border-red-800 rounded-xl p-4 text-red-400 text-sm text-center">
            Failed to load merchants
          </div>
        )}

        {/* ✅ Merchants List */}
        {!isLoading && !error && merchants.length > 0 && (
          <div className="space-y-3">
            {merchants.map((m, idx) => (
              <button
                key={m.id}
                onClick={() => navigate(`/dashboard/${m.id}`)}
                className="w-full flex items-center justify-between p-5 rounded-xl bg-slate-900 border border-slate-800 hover:border-blue-500 transition"
              >
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-lg flex items-center justify-center text-sm font-bold bg-blue-600">
                    {m.name?.charAt(0)}
                  </div>
                  <div className="text-left">
                    <div className="text-white font-semibold text-sm">{m.name}</div>
                    <div className="text-slate-500 text-xs">{m.email}</div>
                  </div>
                </div>
                <ArrowRight size={16} className="text-slate-500" />
              </button>
            ))}
          </div>
        )}

      </div>
    </div>
  );
}