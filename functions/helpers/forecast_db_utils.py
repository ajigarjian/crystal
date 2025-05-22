import logging
from datetime import datetime, timezone
from decimal import Decimal
from .db_utils import execute_query # Assuming this is your existing helper

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
        # Adjust call to match execute_query(query, params=None, fetch_all=True)
        # To fetch one row (for RETURNING run_id), set fetch_all=False.
        # The commit is implicit in the version of execute_query being called.
        result_dict = execute_query(sql, params, fetch_all=False)
        
        if result_dict and 'run_id' in result_dict:
            run_id = result_dict['run_id']
            logger.info(f"Successfully wrote forecast run header. run_id: {run_id}")
            return run_id
        else:
            logger.warning("Write run header did not return a run_id or result was not a dict as expected.")
            # Log the actual result type and content for debugging if it's not None
            if result_dict is not None:
                logger.debug(f"Actual result from execute_query: {result_dict} (type: {type(result_dict)})")
            return None
    except Exception as e:
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
            # Adjust call to match execute_query(query, params=None, fetch_all=True)
            # For a simple INSERT without RETURNING, we don't need to fetch rows.
            # The commit is implicit. Default fetch_all=True is fine.
            execute_query(sql_insert_row, params_for_row)
            rows_written_count += 1
        except Exception as e:
            logger.error(f"Error writing a forecast row for run_id {run_id}, dam_id {dam_id}, valid_utc {aware_valid_utc}: {e}", exc_info=True)

    if rows_written_count > 0:
        logger.info(f"Successfully wrote {rows_written_count} forecast rows for run_id: {run_id}, dam_id: {dam_id}")
    else:
        logger.warning(f"No forecast rows were written for run_id: {run_id}, dam_id: {dam_id}. Input data count: {len(forecast_data)}")