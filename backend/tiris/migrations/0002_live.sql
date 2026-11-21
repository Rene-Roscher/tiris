-- Live samples from get_energy_meter_data (every ~2 s) and their aggregates.
CREATE TABLE power_samples (
    device_id   TEXT NOT NULL,
    ts          TIMESTAMPTZ NOT NULL,
    w           REAL NOT NULL,                -- power, W (plug reports mW)
    v           REAL,                         -- voltage, V
    a           REAL,                         -- current, A
    energy_mwh  BIGINT,                       -- plug counter since its last restart
    delta_mwh   INTEGER NOT NULL DEFAULT 0    -- energy since the previous sample; 0 after a gap or counter reset
);
SELECT create_hypertable('power_samples', by_range('ts', INTERVAL '1 day'));
CREATE INDEX ON power_samples (device_id, ts DESC);

ALTER TABLE power_samples SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'device_id',
    timescaledb.compress_orderby = 'ts'
);
SELECT add_compression_policy('power_samples', INTERVAL '1 day');

-- Minute aggregate from raw samples. Energy is the sum of counter deltas, so it is exact whatever the poll rate.
CREATE MATERIALIZED VIEW power_1m WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT device_id,
       time_bucket(INTERVAL '1 minute', ts) AS bucket,
       avg(w)::real                       AS w_avg,
       min(w)                             AS w_min,
       max(w)                             AS w_max,
       avg(v)::real                       AS v_avg,
       (sum(delta_mwh) / 1000.0)::real    AS wh,
       count(*)                           AS n
FROM power_samples
GROUP BY device_id, bucket
WITH NO DATA;
SELECT add_continuous_aggregate_policy('power_1m',
    start_offset => INTERVAL '3 hours', end_offset => INTERVAL '1 minute', schedule_interval => INTERVAL '1 minute');

-- Hierarchical aggregates; averages weighted by sample count.
CREATE MATERIALIZED VIEW power_15m WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT device_id,
       time_bucket(INTERVAL '15 minutes', bucket) AS bucket,
       (sum(w_avg * n) / NULLIF(sum(n), 0))::real AS w_avg,
       min(w_min)                                 AS w_min,
       max(w_max)                                 AS w_max,
       (sum(v_avg * n) / NULLIF(sum(n), 0))::real AS v_avg,
       sum(wh)::real                              AS wh,
       sum(n)                                     AS n
FROM power_1m
GROUP BY device_id, time_bucket(INTERVAL '15 minutes', bucket)
WITH NO DATA;
SELECT add_continuous_aggregate_policy('power_15m',
    start_offset => INTERVAL '1 day', end_offset => INTERVAL '15 minutes', schedule_interval => INTERVAL '5 minutes');

CREATE MATERIALIZED VIEW power_1h WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT device_id,
       time_bucket(INTERVAL '1 hour', bucket)     AS bucket,
       (sum(w_avg * n) / NULLIF(sum(n), 0))::real AS w_avg,
       min(w_min)                                 AS w_min,
       max(w_max)                                 AS w_max,
       (sum(v_avg * n) / NULLIF(sum(n), 0))::real AS v_avg,
       sum(wh)::real                              AS wh,
       sum(n)                                     AS n
FROM power_15m
GROUP BY device_id, time_bucket(INTERVAL '1 hour', bucket)
WITH NO DATA;
SELECT add_continuous_aggregate_policy('power_1h',
    start_offset => INTERVAL '3 days', end_offset => INTERVAL '1 hour', schedule_interval => INTERVAL '15 minutes');
