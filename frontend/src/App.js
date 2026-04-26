import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import Dashboard from "./components/dashboard/Dashboard";
import MerchantSelect from "./components/dashboard/MerchantSelect";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchInterval: 5000,      // Poll every 5s for live status updates
      retry: 2,
      staleTime: 2000,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<MerchantSelect />} />
          <Route path="/dashboard/:merchantId" element={<Dashboard />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: "#0f1117",
            color: "#e2e8f0",
            border: "1px solid #1e293b",
            fontFamily: "'DM Mono', monospace",
            fontSize: "13px",
          },
        }}
      />
    </QueryClientProvider>
  );
}
