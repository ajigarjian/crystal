import logging
from datetime import datetime, timezone
from decimal import Decimal
from .db_utils import execute_query # Assuming execute_query is in db_utils.py

logger = logging.getLogger(__name__)

def write_run_header(model_id: int, run_issued_utc: datetime, forecast_start_utc: datetime, forecast_end_utc: datetime, horizon_hours: int, lead_time_hours: float, note: dict = None) -> int | None:
    """
    Writes a header row to the fact_forecast_run table and returns the run_id.
    Uses execute_query from db_utils.
    """
    sql = """
        INSERT INTO fact_forecast_run 
        (model_id, run_issued_utc, forecast_start_utc, forecast_end_utc, horizon_hours, lead_time_hours, note)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING run_id;
    """
    # Ensure datetimes are timezone-aware (UTC)
    params = (
        model_id,
        run_issued_utc.astimezone(timezone.utc) if run_issued_utc.tzinfo is None else run_issued_utc,
        forecast_start_utc.astimezone(timezone.utc) if forecast_start_utc.tzinfo is None else forecast_start_utc,
        forecast_end_utc.astimezone(timezone.utc) if forecast_end_utc.tzinfo is None else forecast_end_utc,
        horizon_hours,
        lead_time_hours,
        note
    )
    
    try:
        # execute_query will handle connection and cursor
        # fetch_one=True because RETURNING run_id returns one row
        # commit=True because this is an INSERT statement
        result_dict = execute_query(sql, params, fetch_one=True, commit=True)
        
        if result_dict and 'run_id' in result_dict:
            run_id = result_dict['run_id']
            logger.info(f"Successfully wrote forecast run header. run_id: {run_id}")
            return run_id
        else:
            logger.warning("Write run header did not return a run_id.")
            return None
    except Exception as e:
        # execute_query should raise exceptions from db_utils, which can be caught here
        logger.error(f"Error writing forecast run header using execute_query: {e}", exc_info=True)
        return None

def write_forecast_rows(run_id: int, dam_id: int, metric_id: int, ensemble_member: int, forecast_data: list[dict]):
    """
    Writes multiple forecast data rows to the fact_dam_forecast table.
    Uses execute_query from db_utils for each row.
    """
    sql_insert_row = """
        INSERT INTO fact_dam_forecast
        (run_id, ensemble_member, dam_id, metric_id, valid_utc, value_cfs, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s);
    """
    created_at_ts = datetime.utcnow().replace(tzinfo=timezone.utc)
    rows_written_count = 0

    for row_data in forecast_data:
        valid_utc_val = row_data.get('valid_utc')
        value_cfs_val = row_data.get('value_cfs')

        if not isinstance(valid_utc_val, datetime):
            logger.error(f"Invalid valid_utc type: {type(valid_utc_val)}. Skipping row: {row_data} for run_id {run_id}")
            continue
        
        # Ensure datetime is timezone-aware UTC
        aware_valid_utc = valid_utc_val.astimezone(timezone.utc) if valid_utc_val.tzinfo is None else valid_utc_val

        db_value = None
        if value_cfs_val is not None:
            try:
                db_value = Decimal(str(value_cfs_val))
            except Exception:
                 logger.warning(f"Could not convert value_cfs '{value_cfs_val}' to Decimal for run_id {run_id}. Storing as NULL.")
        
        params_for_row = (
            run_id,
            ensemble_member,
            dam_id,
            metric_id,
            aware_valid_utc,
            db_value,
            created_at_ts
        )
        
        try:
            # Each INSERT is a separate call to execute_query and a separate commit
            execute_query(sql_insert_row, params_for_row, commit=True)
            rows_written_count += 1
        except Exception as e:
            logger.error(f"Error writing a forecast row for run_id {run_id}, dam_id {dam_id}, valid_utc {aware_valid_utc}: {e}", exc_info=True)
            # Continue to try writing other rows, or you might choose to break/return here
            # depending on desired error handling (e.g., if one fails, should all fail?)

    if rows_written_count > 0:
        logger.info(f"Successfully wrote {rows_written_count} forecast rows for run_id: {run_id}, dam_id: {dam_id}")
    else:
        logger.warning(f"No forecast rows were written for run_id: {run_id}, dam_id: {dam_id}. Input data count: {len(forecast_data)}")