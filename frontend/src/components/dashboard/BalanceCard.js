import React from "react";
import { TrendingUp, Lock, Wallet } from "lucide-react";

function fmt(paise) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 2,
  }).format(paise / 100);
}

export default function BalanceCard({ balance }) {
  const cards = [
    {
      label: "Available Balance",
      value: fmt(balance.available_paise),
      sub: `${balance.available_paise.toLocaleString("en-IN")} paise`,
      icon: Wallet,
      color: "blue",
      glow: "#3b82f6",
    },
    {
      label: "Held (In-Flight)",
      value: fmt(balance.held_paise),
      sub: "Pending + Processing payouts",
      icon: Lock,
      color: "amber",
      glow: "#f59e0b",
    },
    {
      label: "Total Received",
      value: fmt(balance.total_credits_paise),
      sub: `${fmt(balance.total_debits_paise)} paid out`,
      icon: TrendingUp,
      color: "emerald",
      glow: "#10b981",
    },
  ];

  const colorMap = {
    blue: {
      bg: "bg-blue-500/10",
      border: "border-blue-500/20",
      icon: "text-blue-400",
      value: "text-blue-300",
    },
    amber: {
      bg: "bg-amber-500/10",
      border: "border-amber-500/20",
      icon: "text-amber-400",
      value: "text-amber-300",
    },
    emerald: {
      bg: "bg-emerald-500/10",
      border: "border-emerald-500/20",
      icon: "text-emerald-400",
      value: "text-emerald-300",
    },
  };

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      {cards.map((card) => {
        const c = colorMap[card.color];
        const Icon = card.icon;
        return (
          <div
            key={card.label}
            className={`rounded-xl border ${c.border} ${c.bg} p-5 backdrop-blur-sm`}
          >
            <div className="flex items-center justify-between mb-4">
              <span className="text-slate-400 text-xs font-mono uppercase tracking-widest">
                {card.label}
              </span>
              <Icon size={16} className={c.icon} />
            </div>
            <div className={`text-2xl font-bold ${c.value} tracking-tight`}>
              {card.value}
            </div>
            <div className="text-slate-600 text-xs font-mono mt-1">{card.sub}</div>
          </div>
        );
      })}
    </div>
  );
}
