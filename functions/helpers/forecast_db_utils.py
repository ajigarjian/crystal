import os
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict, Any, Optional

import psycopg2
from psycopg2 import pool, OperationalError
from psycopg2.extras import RealDictCursor

# Import the centralized connection pool from db_utils
from .db_utils import get_connection_pool

"""forecast_db_utils.py – *stand‑alone* helpers for writing forecast metadata
and rows to PostgreSQL / Cloud SQL.

Environment variables expected (same names used by Cloud SQL Python Connector
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
    # Use the imported get_connection_pool
    current_pool = get_connection_pool() 
    try:
        conn = current_pool.getconn()
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
            current_pool.putconn(conn)


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
    note: Optional[str] = None,
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
        (run_id, dam_id, ensemble_member, 
         valid_utc, value_cfs)
        VALUES (%s, %s, %s, %s, %s);
        """
    )

    rows_written = 0

    for row_data_point in forecast_data:
        valid_ts = row_data_point.get("valid_utc")
        value_cfs = row_data_point.get("value_cfs")

        if not isinstance(valid_ts, datetime):
            logger.error("Row skipped – valid_utc is not datetime: %s", row_data_point)
            continue

        params = (
            run_id,
            dam_id,
            ensemble_member,
            valid_ts.astimezone(timezone.utc),
            Decimal(str(value_cfs)) if value_cfs is not None else None,
        )
        try:
            _execute(sql, params, fetch_all=False)
            rows_written += 1
        except Exception:
            # Error already logged in _execute
            continue

    logger.info("%s forecast rows written for run_id=%s (dam_id=%s)", rows_written, run_id, dam_id)
