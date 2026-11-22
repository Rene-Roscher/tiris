# tiris

Local-first energy monitor for TP-Link Tapo smart plugs: history, live power, device control and costs, in one
small app for your home lab.

- **History** – hourly, daily and monthly energy as far back as each plug keeps it, checked before it is stored.
- **Live** – power, voltage, current and power factor every 2 seconds, stored and aggregated in TimescaleDB.
- **Analysis** – per device: power curve, voltage, on/off cycles, duty cycle, typical run time, daily energy.
- **Devices** – rename, switch, timers, schedules, restart, firmware updates, rooms and categories, and a
  protection that keeps a fridge from being switched off by accident.
- **Costs** – meters for electricity and gas, tariffs and installment plans with validity periods, meter
  readings, payments, cost per device and month, and a forecast of the yearly bill.

Everything stays in your network. tiris talks to the plugs directly; the Tapo account is only used for the
plug's local handshake. No cloud calls, no telemetry.

Supported: P110, P110M, P115, and the sockets of P304M / P316M (anything the
[`tapo`](https://github.com/mihai-dinculescu/tapo) library supports with energy monitoring).

## Quick start

Requirements: Docker, a machine in the same network as the plugs (discovery uses UDP broadcasts).

```bash
git clone <this repository> tiris && cd tiris
cp .env.example .env        # your Tapo account and your subnet broadcast, e.g. 192.168.1.255
docker compose up -d --build
```

Open `http://<host>:8080`. The first fetch runs at start and reads as much history as the plugs keep; live values
appear within seconds. Then add your electricity meter, tariff and a meter reading under **Costs**.

## How it works

| Source on the plug | Resolution | The plug keeps | tiris |
|---|---|---|---|
| live meter (`get_energy_meter_data`) | power, voltage, current, energy counter | now | polled every 2 s; energy from the counter, so it is exact whatever the poll rate |
| 5-minute power buffer | 5 min | about 10 days | read every 15 min; fills gaps when tiris was down |
| hourly energy | 1 h | about 8 days (busy plugs) to 30 days | read every 15 min |
| daily energy | 1 day | about 3 months (busy) to 8 months | read every 15 min |
| monthly energy | 1 month | 13 to 22 months | read every 15 min |

Values measured on P110 plugs with firmware 1.4.7 and 1.4.8. Plugs keep a number of entries rather than a time
span, so rarely used plugs reach further back.

What tiris checks before storing history:

- **Cross-level validation.** Each daily window is checked against the monthly values, each hourly window
  against the daily values. On real plugs, daily windows older than a year came back shifted by about a month;
  such windows are dropped.
- **Replay guard.** An older window that repeats a newer one is dropped.
- **Never shrink.** Values are upserted with `GREATEST`, so a plug reset or "delete energy data" in the app does
  not erase stored history.
- **Zeros only where certain.** Beyond its memory a plug returns 0 instead of "unknown"; tiris stores zeros only
  inside the part the plug surely still holds.

Storage: raw samples are compressed after a day and kept for `TIRIS_RAW_RETENTION_DAYS` (365 by default);
minute, 15-minute and hourly aggregates are kept forever. 20 plugs produce about 1.15 million raw rows a day,
a few GB a year after compression (estimate).

## Configuration

All settings are environment variables (`.env`). Plugs, meters, tariffs and the rest are set up in the UI.

| Variable | Default | Meaning |
|---|---|---|
| `TIRIS_TAPO_USERNAME`, `TIRIS_TAPO_PASSWORD` | – | the Tapo account the plugs are bound to |
| `TIRIS_DISCOVERY_TARGETS` | `255.255.255.255` | subnet broadcast and/or fixed plug IPs, comma separated |
| `TIRIS_PASSWORD` | empty | password for the UI; empty means no login |
| `TIRIS_TIMEZONE` | `Europe/Berlin` | day boundaries and schedules |
| `TIRIS_LIVE_INTERVAL_S` | `2` | live poll interval; plugs update their power value about every 1.5 s |
| `TIRIS_COLLECT_INTERVAL_MIN` | `15` | history fetch interval |
| `TIRIS_RAW_RETENTION_DAYS` | `365` | how long raw 2-second samples are kept |
| `TIRIS_PORT` | `8080` | HTTP port |

## Security

tiris is made for a trusted home network. It binds to all interfaces of the host; put it behind your reverse
proxy for anything else. With `TIRIS_PASSWORD` set, the UI and API require a login (HttpOnly, SameSite=Strict
session cookie). Device actions that cut power (switch off, restart, firmware update) ask for confirmation, and
protected devices refuse them on the server. Factory reset is not offered.

## Running it somewhere else (VPS, cloud)

tiris has to reach the plugs on your home network: it talks to each plug's local API and finds them by UDP
broadcast. A server at a hosting provider cannot see your LAN, so on its own it cannot track anything. It works
through a VPN:

1. Connect the server to your home network with WireGuard or Tailscale (a router with WireGuard, or a small
   always-on device at home as subnet router).
2. Give the plugs fixed addresses (DHCP reservations in the router) and list them in `TIRIS_DISCOVERY_TARGETS`,
   e.g. `192.168.1.40,192.168.1.41`. Broadcasts do not cross the tunnel; unicast discovery does.
3. Set `TIRIS_PASSWORD` and put tiris behind a reverse proxy with HTTPS. Do not expose port 8080 directly; the
   server then also holds your Tapo account credentials.

What to expect: live polling is ten small requests every 2 s, a few kB/s; round trips of 20 to 40 ms over the
tunnel are fine. When the tunnel drops, live samples are missing for that time, but history is not lost: each
plug keeps about 10 days of 5-minute power and its hourly, daily and monthly energy, and tiris backfills them
on the next fetch. Running tiris at home and only viewing it remotely (through the same VPN) is simpler and
keeps the credentials at home.

Only one tiris process may talk to the plugs per database. A second one (say, a test container on the same
database) waits instead of polling: it would otherwise count energy twice and evict the first one's sessions.

## Development

```bash
# backend (Python 3.12, uv)
cd backend && uv sync
TIRIS_DATABASE_URL=postgresql://... uv run python -c "from tiris.main import run; run()"
TIRIS_TEST_DATABASE_URL=postgresql://.../empty_db uv run pytest   # drops that database's schema

# web (Node 22, pnpm)
cd web && pnpm install && pnpm dev        # proxies /api to TIRIS_API (default http://127.0.0.1:8080)
```

Stack: FastAPI, psycopg, TimescaleDB; Vue 3, TypeScript, Tailwind CSS 4, shadcn-vue on Reka UI, ECharts,
vue-i18n (English, German). Design decisions are in [docs/PLAN.md](docs/PLAN.md).

## License

MIT. tiris is not affiliated with or endorsed by TP-Link. "Tapo" is a trademark of TP-Link.
