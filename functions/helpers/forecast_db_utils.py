import os
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict, Any, Optional

import psycopg2
from psycopg2 import pool, OperationalError
from psycopg2.extras import RealDictCursor

"""forecast_db_utils.py – *stand‑alone* helpers for writing forecast metadata
and rows to PostgreSQL / Cloud SQL.

Environment variables expected (same names used by Cloud SQL Python Connector
& Cloud Functions examples):
    DB_NAME       – database name
    DB_USER       – role / user name
    DB_PASSWORD   – password for that user
    DB_INSTANCE   – instance connection name  (project:region:instance)
    DB_HOST       – **optional**; if set we connect via TCP instead of Unix‑socket
    DB_PORT       – **optional**; defaults to 5432

Usage::

    from forecast_db_utils import write_run_header, write_forecast_rows

    run_id = write_run_header(...)
    write_forecast_rows(run_id, ...)
"""

logger = logging.getLogger(__name__)

# 🚨  Hard-coded fallback
_HARDCODED_DB = {
    "NAME": "crystal",
    "USER": "postgres",
    "PASSWORD": "A$icV~t||V7RT-",
    "INSTANCE": "crystal-2f87e:us-east4:crystal-sql",  # leave empty if using TCP
    "HOST": "",     # e.g. "34.48.13.135"  • leave "" to prefer Unix socket
    "PORT": 5432,
}
# ----

# ------------------------------------------------------------
# Connection handling
# ------------------------------------------------------------
_pool: Optional[pool.ThreadedConnectionPool] = None

def _create_pool(min_conn: int = 1, max_conn: int = 10) -> pool.ThreadedConnectionPool:
    """Create a connection pool.

    Preference order:
        1. Unix‑domain socket at /cloudsql/<instance>
        2. TCP using DB_HOST / DB_PORT (public or private IP)
    """
    db_name     = os.getenv("DB_NAME",     _HARDCODED_DB["NAME"])
    db_user     = os.getenv("DB_USER",     _HARDCODED_DB["USER"])
    db_pwd      = os.getenv("DB_PASSWORD", _HARDCODED_DB["PASSWORD"])
    db_instance = os.getenv("DB_INSTANCE", _HARDCODED_DB["INSTANCE"])
    db_host     = os.getenv("DB_HOST",     _HARDCODED_DB["HOST"])
    db_port     = int(os.getenv("DB_PORT", str(_HARDCODED_DB["PORT"])))

    # 1️⃣  Unix‑socket (Cloud Functions Gen 1/2 with --set-cloudsql-instances / --connections)
    if db_instance and not db_host:
        socket_dir = os.getenv("DB_SOCKET_DIR", "/cloudsql")
        socket_path = f"{socket_dir}/{db_instance}"
        try:
            logger.info("Connecting to Cloud SQL over Unix socket %s", socket_path)
            return pool.ThreadedConnectionPool(
                min_conn,
                max_conn,
                dbname=db_name,
                user=db_user,
                password=db_pwd,
                host=socket_path,
            )
        except OperationalError as err:
            logger.warning("Unix‑socket connection failed – %s", err)

    # 2️⃣  TCP (public / private address)
    host = db_host or "127.0.0.1"
    logger.info("Connecting to PostgreSQL over TCP %s:%s", host, db_port)
    return pool.ThreadedConnectionPool(
        min_conn,
        max_conn,
        dbname=db_name,
        user=db_user,
        password=db_pwd,
        host=host,
        port=db_port,
        sslmode="require" if os.getenv("DB_SSL", "true").lower() in {"1", "true", "yes"} else "prefer",
    )


def _get_pool() -> pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = _create_pool()
    return _pool


# ------------------------------------------------------------
# Low‑level helper
# ------------------------------------------------------------

def _execute(query: str, params: tuple | None = None, fetch_all: bool = True) -> Any:
    """Execute *query* inside a pooled connection.

    When *fetch_all* is False return the first row (or None).
    Uses RealDictCursor so we can refer to columns by name.
    """
    conn = None
    cur = None
    try:
        conn = _get_pool().getconn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(query, params)
        if cur.description:  # SELECT / RETURNING
            result = cur.fetchall() if fetch_all else cur.fetchone()
        else:
            result = None
        conn.commit()
        return result
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("SQL execution failed: %s", e, exc_info=True)
        raise
    finally:
        if cur:
            cur.close()
        if conn:
            _get_pool().putconn(conn)


# ------------------------------------------------------------
# Public helpers used by your forecast functions
# ------------------------------------------------------------

def write_run_header(
    model_id: int,
    run_issued_utc: datetime,
    forecast_start_utc: datetime,
    forecast_end_utc: datetime,
    horizon_hours: int,
    lead_time_hours: float,
    note: Optional[dict] = None,
) -> Optional[int]:
    """Insert a record into **fact_forecast_run** and return the generated *run_id*."""
    sql = (
        """
        INSERT INTO fact_forecast_run
        (model_id, run_issued_utc, forecast_start_utc, forecast_end_utc,
         horizon_hours, lead_time_hours, note)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING run_id;
        """
    )

    params = (
        model_id,
        run_issued_utc.astimezone(timezone.utc),
        forecast_start_utc.astimezone(timezone.utc),
        forecast_end_utc.astimezone(timezone.utc),
        horizon_hours,
        lead_time_hours,
        note,
    )

    result = _execute(sql, params, fetch_all=False)
    if result and result.get("run_id") is not None:
        run_id = result["run_id"]
        logger.info("Forecast run header written (run_id=%s)", run_id)
        return run_id

    logger.error("Failed to obtain run_id from INSERT RETURNING – result=%s", result)
    return None


def write_forecast_rows(
    run_id: int,
    dam_id: int,
    metric_id: int,
    ensemble_member: int,
    forecast_data: List[Dict[str, Any]],
):
    """Bulk‑insert hourly forecast rows into **fact_dam_forecast**."""
    if not forecast_data:
        logger.warning("No forecast rows provided – nothing written (run_id=%s)", run_id)
        return

    sql = (
        """
        INSERT INTO fact_dam_forecast
        (run_id, ensemble_member, dam_id, metric_id,
         valid_utc, value_cfs, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s);
        """
    )

    created_at = datetime.utcnow().replace(tzinfo=timezone.utc)
    rows_written = 0

    for row in forecast_data:
        valid_ts = row.get("valid_utc")
        value_cfs = row.get("value_cfs")
        if not isinstance(valid_ts, datetime):
            logger.error("Row skipped – valid_utc is not datetime: %s", row)
            continue

        params = (
            run_id,
            ensemble_member,
            dam_id,
            metric_id,
            valid_ts.astimezone(timezone.utc),
            Decimal(str(value_cfs)) if value_cfs is not None else None,
            created_at,
        )
        try:
            _execute(sql, params, fetch_all=False)
            rows_written += 1
        except Exception:
            # Error already logged in _execute
            continue

    logger.info("%s forecast rows written for run_id=%s (dam_id=%s)", rows_written, run_id, dam_id)
