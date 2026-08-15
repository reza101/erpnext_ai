# ERPNext AI Integration Module

Custom Frappe app providing LLM-powered features across ERPNext modules
(Stock, Accounts, Sales, Buying, HR, Reporting), backed by OpenAI.

## Status

Phase 1 (this build): global architecture only.

- **AI Settings** (`AI Settings`, Single doctype) — central config: API key,
  model, temperature, which Role is allowed to use the assistant, and whether
  the floating chat widget is shown.
- **AI Chat Log** (`AI Chat Log`) — audit trail of every prompt/response pair,
  owned by the requesting user.
- **Floating chat widget** — injected into the Desk UI for users holding the
  configured role, calls a whitelisted API that enforces that role check
  server-side (the client-side visibility toggle is UX only, not the
  permission boundary).
- **Background job plumbing** (`erpnext_ai.tasks.enqueue_ai_job`) — generic
  helper for future heavy/async AI work (OCR, forecasting, RFQ generation,
  etc.) so those features don't block the request thread.

Everything module-specific (Stock anomaly detection, Purchase Invoice OCR,
lead scoring, resume parsing, text-to-SQL reporting, ...) described in the
original development request is intentionally **not** built yet — this phase
only lays the foundation those features will plug into.

## Setup

1. Install the app on your site: `bench --site <site> install-app erpnext_ai`
2. Open **AI Settings**, paste an OpenAI API key, pick a model, tick
   **Enabled**, and set **Allowed Role** (defaults to `System Manager`).
3. Users holding that role will see a floating chat button on the Desk.

## Adding a new AI feature module

Call `erpnext_ai.llm.chat_completion(messages)` for a synchronous request, or
wrap long-running work in `erpnext_ai.tasks.enqueue_ai_job(method, **kwargs)`
so it runs on the `long` queue instead of blocking a web worker.
