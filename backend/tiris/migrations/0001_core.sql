-- Core: devices, device history from the plugs, collector runs, settings.
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE devices (
    device_id   TEXT PRIMARY KEY,
    parent_id   TEXT,                         -- set for sockets of a power strip (P304M, P316M)
    position    INTEGER,
    nickname    TEXT,
    model       TEXT,
    ip          TEXT,
    mac         TEXT,
    fw_ver      TEXT,
    hw_ver      TEXT,
    timezone    TEXT,                         -- IANA zone of the device; decides its day boundaries
    room        TEXT,
    category    TEXT,
    note        TEXT,
    protected   BOOLEAN NOT NULL DEFAULT FALSE,   -- never switched off from tiris
    retired     BOOLEAN NOT NULL DEFAULT FALSE,
    first_seen  TIMESTAMPTZ NOT NULL,
    last_seen   TIMESTAMPTZ NOT NULL
);

-- History as the plug reports it. Upserts keep GREATEST(old, new): values only grow from partial to final,
-- and a reset plug reports zeros that must not overwrite stored history.
CREATE TABLE energy_hourly (
    device_id   TEXT NOT NULL,
    ts          TIMESTAMPTZ NOT NULL,         -- start of the hour
    wh          INTEGER NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (device_id, ts)
);
SELECT create_hypertable('energy_hourly', by_range('ts', INTERVAL '365 days'));

CREATE TABLE energy_daily (
    device_id   TEXT NOT NULL,
    day         DATE NOT NULL,                -- local date in the device timezone
    wh          INTEGER NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (device_id, day)
);

CREATE TABLE energy_monthly (
    device_id   TEXT NOT NULL,
    month       DATE NOT NULL,                -- first day of the month
    wh          INTEGER NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (device_id, month)
);

-- 5-minute average power from the plug's own buffer (~10 days). Fills gaps when tiris was not running.
CREATE TABLE power_5min (
    device_id   TEXT NOT NULL,
    ts          TIMESTAMPTZ NOT NULL,
    w           INTEGER NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (device_id, ts)
);
SELECT create_hypertable('power_5min', by_range('ts', INTERVAL '30 days'));

CREATE TABLE runs (
    id              BIGSERIAL PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL,
    finished_at     TIMESTAMPTZ,
    status          TEXT,                     -- ok | partial | failed
    devices_ok      INTEGER,
    devices_failed  INTEGER,
    message         TEXT
);

CREATE TABLE settings (
    key         TEXT PRIMARY KEY,
    value       JSONB NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
