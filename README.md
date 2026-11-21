# tiris

Local-first energy monitor for TP-Link Tapo smart plugs (P110, P110M, P115 and the sockets of P304M / P316M).

- **History:** hourly, daily and monthly energy as far back as each plug keeps it, checked for misdated windows.
- **Live:** power, voltage, current and power factor every 2 seconds, stored and aggregated (TimescaleDB).
- **Devices:** rename, switch, timers, schedules, firmware, protection against switching off by accident.
- **Costs:** tariffs, meter readings, installment plans and payments; forecast of the yearly bill.

Everything runs in your network. No cloud account access beyond the plug handshake, no telemetry.

> Status: early development. See [docs/PLAN.md](docs/PLAN.md).

## Run

```bash
cp .env.example .env    # Tapo account and your subnet broadcast
docker compose up -d --build
```

Open http://<host>:8080.

## Development

```bash
cd backend && uv sync && uv run python -c "from tiris.main import run; run()"
```

## License

MIT. Not affiliated with TP-Link. "Tapo" is a trademark of TP-Link.
