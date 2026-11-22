# tiris – Plan

Local-first energy monitor for TP-Link Tapo smart plugs: history, live power, device control, costs, bills.
Runs in a home lab next to the plugs. MIT licensed.

This plan carries the decisions from an earlier prototype (measured on real P110 plugs,
FW 1.4.7/1.4.8, 2026-11-21). Facts measured there are marked [measured]; everything else is a decision.

## Goals

1. Keep every value the plugs expose, at the finest resolution they offer, for as long as the user wants.
2. Show it in a dense, calm, fast UI: overview, live, devices, costs.
3. Answer money questions: what does each device cost, will the yearly bill bring a back payment.
4. Work for anyone with Tapo plugs: no personal data in the repo, setup in the UI.

Non-goals (v1): cloud access, multi-user accounts, other plug brands, a mobile app.

## What the plugs offer [measured]

| Source | Resolution | Device keeps | Notes |
|---|---|---|---|
| `get_energy_meter_data` | power in mW, voltage, current, energy counter in mWh | live only | 11 ms per call; power value updates about every 1.5 s, the counter every ~0.5 s in ~39 mWh steps |
| `get_power_data(Every5Minutes)` | W per 5 min | ~10 days | 144 entries per call; matches hourly energy within ±3 % on 75–83 % of hours (rounding) |
| `get_energy_data(Hourly)` | Wh per hour | ~8 days (busy plugs) to ~30 days (rarely used) | window ≤ 8 days |
| `get_energy_data(Daily)` | Wh per day | ~92 days (busy) to ~8 months (rare) | start = quarter start; windows older than a year come back shifted by about a month |
| `get_energy_data(Monthly)` | Wh per month | 13 to 22 months | start = year start |
| `get_device_info`, timer, schedules, firmware | state | – | firmware check blocks the plug for up to ~10 s and often fails with -1001 |

Consequences:
- Poll live every 2 s (the plug does not update faster). Energy comes from the mWh counter, so energy and cost
  are exact whatever the poll interval; the interval only decides the detail of the power curve.
- Collect history every 15 min: hourly/daily/monthly with cross-level validation, plus
  the 5-minute buffer, so an outage of the app up to ~10 days loses no 5-minute detail.
- No rate limits: everything is local. The only cloud call is the plug's own firmware check (daily, serial).

## Decisions

| # | Decision | Why | Alternative rejected |
|---|---|---|---|
| D1 | Python 3.12 + FastAPI backend, one process: API, collector schedule, live poller | the `tapo` library is Python (Rust core); one container is easy to run in a home lab | separate services (more ops), Node (no maintained TPAP library) |
| D2 | PostgreSQL 18 + TimescaleDB 2.24: hypertables, compression, continuous aggregates | 20 plugs at one sample per 1.5 s is ~1.15 M rows/day; compressed this is a few GB/year (estimate, to be measured) | ClickHouse: second database, no gain at this size |
| D3 | Raw samples stored on change, aggregates 1 min / 15 min / 1 h / 1 day computed by Timescale | UI reads aggregates, never raw rows, except the live window | storing only minute averages (loses detail) |
| D4 | Vue 3 + TypeScript 5.9 + Vite 8 + Tailwind 4, shadcn-vue on Reka UI, `@lucide/vue`, ECharts via vue-echarts, vue-i18n (de, en), TanStack Query, VueUse | favorites from `web/vue-inertia-frontend` (Rene-Roscher/skills) | TS 7 (vue-tsc needs the TS 5 JS API) |
| D5 | Toasts: the toast pill from the `ui-motion` example (Rene-Roscher/skills) on vue-sonner, ported to tiris tokens; a press while it springs back catches it on screen, the waiting pill follows the same spring and keeps the peek its width shows; measured with `catchTest` in Chromium, Firefox, WebKit | a tested pattern; the catch fixes a jump of the original | default Sonner look |
| D6 | Motion per `web/interface-motion`: curve tokens (`quick`, `settle` 0.30 s, `calm` 0.35 s, bounce 0) with `cubic-bezier()` fallback, springs generated as `linear()` at startup (`lib/motion.ts`, vendored `spring.mjs`); dialogs, confirm and sheet use transitions, short popovers and menus keep keyframes from their trigger; measured in Chromium, Firefox, WebKit with and without reduced motion | no animation library; transitions start from the value on screen | Motion; keyframes on interruptible overlays |
| D7 | Setup in the UI (plugs, tariffs, meters); `.env` only for DB URL and Tapo account | open source users should not edit files | everything in `.env` |
| D8 | Security for a home lab: bind to the LAN, optional single password (session cookie), CSRF-safe JSON API, no secrets in the browser | a home lab needs little protection, but not none | no auth at all; full user management |
| D9 | Costs model: meters (electricity, gas) with readings; tariffs with validity; installment plans with from/to dates; payments ledger; forecast = plugs measured + unmetered rest per day (additive, calibrated on meter intervals) | additive model matched the meter exactly in the prototype; proportional model mis-scaled summer AC | proportional coverage |
| D10 | Name `tiris`; "Tapo" only in the description | "Tapo" is a TP-Link trademark | `tapo-view` |
| D11 | Demo mode (`TIRIS_DEMO`): one behaviour model per made-up device seeds 14 months of history and drives simulated plugs | README images and a try-out without plugs, without anyone's real data | static screenshots of a real home |

## Data model (v1)

- `devices`: id, parent, model, ip, mac, fw/hw, timezone, nickname, room, category, note, protected, retired, color
  slot, first/last seen.
- `power_samples` (hypertable, compressed after 1 day): device, ts, w, v, a, energy_mwh, delta_mwh (0 on counter
  reset).
- Continuous aggregates: `power_1m`, `power_15m`, `power_1h`, `power_1d` (avg/min/max W, sum of delta Wh,
  samples).
- `power_5min` (hypertable): device buffer, fills gaps when the app was down.
- `energy_hourly`, `energy_daily`, `energy_monthly`: device history with GREATEST upserts and validation.
- `meters`: kind (electricity, gas), name, unit, gas conversion (calorific value, z-number).
- `meter_readings`: meter, date, value, estimated, note.
- `tariffs`: meter, valid_from, valid_to, provider, name, energy price net, base price net/year, VAT, contract end.
- `installment_plans`: meter, valid_from, valid_to, amount gross, day of month.
- `payments`: date, amount (negative = refund), kind (installment, settlement, other), meter, note, external ref.
- `settings`, `runs`.

## Phases

1. Backend core: config, DB + migrations, Tapo client pool, collector (port with tests), live poller with raw
   samples and aggregates, devices, costs, API.
2. Frontend foundation: tokens (light/dark, measured), type scale, layout shell (sidebar, header), state
   components (skeleton, empty, error), toast pill, chart theme.
3. Views: overview, live, devices (control), costs (bills, installments, readings, payments), settings
   (plugs discovery, tariffs, retention).
4. Quality: design audit and browser measurement in light/dark, tests, CI, Docker image, README with
   screenshots.

## Design references (design-quality, dashboards)

- Grafana Saga / Sentry: data density, chart states.
- Vercel (Geist) / Linear: neutral ramp with step roles, receding chrome, one accent, 14 px app text.
- Laravel Cloud: calm surfaces, restrained colour.
Principles only, no brand looks.

## Open questions

- Default retention of raw samples (proposal: 365 days, configurable; aggregates forever).
- Password protection on by default? (proposal: off on first start, prompt in settings).
