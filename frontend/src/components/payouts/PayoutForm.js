import React, { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createPayout } from "../../services/api";
import toast from "react-hot-toast";
import { Send, AlertCircle } from "lucide-react";

function generateIdempotencyKey() {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export default function PayoutForm({ merchant }) {
  const qc = useQueryClient();
  const [amountRupees, setAmountRupees] = useState("");
  const [selectedAccount, setSelectedAccount] = useState(
    merchant.bank_accounts?.[0]?.id ?? ""
  );
  const [lastKey, setLastKey] = useState(generateIdempotencyKey());

  const mutation = useMutation({
    mutationFn: (vars) => createPayout(vars),
    onSuccess: (data) => {
      toast.success(`Payout of ${data.amount_inr} queued — ID: ${data.id.slice(0, 8)}…`);
      setAmountRupees("");
      setLastKey(generateIdempotencyKey());
      qc.invalidateQueries({ queryKey: ["merchant", merchant.id] });
      qc.invalidateQueries({ queryKey: ["payouts", merchant.id] });
      qc.invalidateQueries({ queryKey: ["ledger", merchant.id] });
    },
    onError: (err) => {
      const msg = err?.response?.data?.error ?? "Failed to create payout.";
      toast.error(msg);
    },
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    const rupees = parseFloat(amountRupees);
    if (isNaN(rupees) || rupees <= 0) {
      toast.error("Enter a valid amount.");
      return;
    }
    const amountPaise = Math.round(rupees * 100);
    const available = merchant.balance?.available_paise ?? 0;
    if (amountPaise > available) {
      toast.error(`Insufficient balance. Available: ₹${(available / 100).toFixed(2)}`);
      return;
    }
    mutation.mutate({
      merchantId: merchant.id,
      amount_paise: amountPaise,
      bank_account_id: selectedAccount,
      idempotencyKey: lastKey,
    });
  };

  const available = merchant.balance?.available_paise ?? 0;
  const accounts = merchant.bank_accounts ?? [];

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
      <h2 className="text-white font-semibold text-sm mb-5 flex items-center gap-2">
        <Send size={15} className="text-blue-400" />
        Request Payout
      </h2>

      <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-3 items-end">
        {/* Amount */}
        <div className="flex-1">
          <label className="block text-xs font-mono text-slate-500 mb-1.5 uppercase tracking-wider">
            Amount (₹)
          </label>
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 font-mono text-sm">
              ₹
            </span>
            <input
              type="number"
              step="0.01"
              min="1"
              value={amountRupees}
              onChange={(e) => setAmountRupees(e.target.value)}
              placeholder="0.00"
              className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-7 pr-4 py-2.5 text-white font-mono text-sm placeholder-slate-600 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30 transition-colors"
            />
          </div>
          <div className="text-xs font-mono text-slate-600 mt-1">
            Available: ₹{(available / 100).toFixed(2)}
          </div>
        </div>

        {/* Bank account */}
        <div className="flex-1">
          <label className="block text-xs font-mono text-slate-500 mb-1.5 uppercase tracking-wider">
            Bank Account
          </label>
          <select
            value={selectedAccount}
            onChange={(e) => setSelectedAccount(e.target.value)}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 text-white font-mono text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30 transition-colors"
          >
            {accounts.map((acct) => (
              <option key={acct.id} value={acct.id}>
                {acct.bank_name} {acct.masked_account}
              </option>
            ))}
          </select>
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={mutation.isPending || !selectedAccount}
          className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-500 text-white font-mono text-sm rounded-lg transition-colors flex items-center gap-2 whitespace-nowrap"
        >
          {mutation.isPending ? (
            <>
              <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Sending...
            </>
          ) : (
            <>
              <Send size={13} />
              Send Payout
            </>
          )}
        </button>
      </form>

      {/* Idempotency key display */}
      <div className="mt-3 flex items-center gap-2 text-slate-600 text-xs font-mono">
        <AlertCircle size={11} />
        Idempotency Key: {lastKey.slice(0, 18)}…
      </div>
    </div>
  );
}
