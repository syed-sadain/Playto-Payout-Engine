import axios from "axios";

const BASE_URL = process.env.REACT_APP_API_URL || "/api/v1";

const api = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
});

// ─── Merchants ────────────────────────────────────────────────────────────────

export const fetchMerchants = () =>
  api.get("/merchants/").then((r) => r.data);

export const fetchMerchant = (merchantId) =>
  api.get(`/merchants/${merchantId}/`).then((r) => r.data);

export const fetchLedger = (merchantId) =>
  api.get(`/merchants/${merchantId}/ledger/`).then((r) => r.data);

// ─── Payouts ─────────────────────────────────────────────────────────────────

export const fetchPayouts = (merchantId) =>
  api.get(`/merchants/${merchantId}/payouts/`).then((r) => r.data);

export const createPayout = ({ merchantId, amount_paise, bank_account_id, idempotencyKey }) =>
  api
    .post(
      `/merchants/${merchantId}/payouts/`,
      { amount_paise, bank_account_id },
      { headers: { "Idempotency-Key": idempotencyKey } }
    )
    .then((r) => r.data);

export const fetchPayout = (merchantId, payoutId) =>
  api.get(`/merchants/${merchantId}/payouts/${payoutId}/`).then((r) => r.data);

export default api;
