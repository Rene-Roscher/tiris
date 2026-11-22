"""Shared test helpers."""
import time

import psycopg


def reset_database(url: str) -> None:
    """Empty the test database. TimescaleDB runs policy jobs (aggregate refresh, compression) in background workers;
    one of them can hold a lock on a table the DROP needs, which ends in a deadlock. So the jobs are removed first,
    and the reset is retried if a running job still gets in the way."""
    for attempt in range(6):
        try:
            with psycopg.connect(url, autocommit=True) as con:
                if con.execute("SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'").fetchone():
                    con.execute("SELECT delete_job(job_id) FROM timescaledb_information.jobs WHERE job_id >= 1000")
                con.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
            return
        except (psycopg.errors.DeadlockDetected, psycopg.errors.LockNotAvailable):
            if attempt == 5:
                raise
            time.sleep(0.5 * (attempt + 1))
