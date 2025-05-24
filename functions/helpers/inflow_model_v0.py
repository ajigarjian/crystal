import requests
from datetime import datetime, timedelta, timezone
import logging
import math

logger = logging.getLogger(__name__)

# Basin points and lags for Grand Coulee (dam_id=1)
# These would need to be configurable if supporting other dams in the future.
GRAND_COULEE_POINTS = [
    {"name": "Columbia at Hunters", "lat": 47.860, "lon": -118.220, "p_weight": 0.30, "s_weight": 0.15, "lag_days": 0.2},
    {"name": "Sanpoil at Keller", "lat": 47.955, "lon": -118.700, "p_weight": 0.08, "s_weight": 0.03, "lag_days": 0.3},
    {"name": "Lake Roosevelt at Marcus", "lat": 48.668, "lon": -118.057, "p_weight": 0.12, "s_weight": 0.07, "lag_days": 0.5},
    {"name": "Columbia at Northport", "lat": 48.915, "lon": -117.793, "p_weight": 0.13, "s_weight": 0.09, "lag_days": 1.0},
    {"name": "Kettle River at Laurier", "lat": 48.900, "lon": -118.457, "p_weight": 0.07, "s_weight": 0.07, "lag_days": 1.2},
    {"name": "Pend Oreille at Newport", "lat": 48.180, "lon": -117.043, "p_weight": 0.10, "s_weight": 0.09, "lag_days": 1.2},
    {"name": "Spokane River at Spokane", "lat": 47.660, "lon": -117.400, "p_weight": 0.10, "s_weight": 0.05, "lag_days": 1.0},
    {"name": "Columbia at Kettle Falls", "lat": 48.617, "lon": -118.054, "p_weight": 0.10, "s_weight": 0.08, "lag_days": 0.8}
]

# Model parameters (these can be tuned or made configurable)
RUNOFF_COEFF = 0.4
SNOWMELT_COEFF = 0.35
SCALING_FACTOR = 48.0
SNOWMELT_THRESH_TEMP_C = 1.0 # Temperature (Celsius) above which snowmelt occurs
HOURLY_ROLLING_AVG_WINDOW_SNOWMELT = 7 * 24 # 7 days in hours

def fetch_hourly_weather(lat, lon, start_date_str: str, end_date_str: str) -> tuple[list, list, list]:
    """Fetches hourly precipitation and temperature from Open-Meteo."""
    # API documentation: https://open-meteo.com/en/docs
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}&start_date={start_date_str}&end_date={end_date_str}"
        f"&hourly=precipitation,temperature_2m"
        f"&timezone=UTC"
        f"&models=gfs_seamless"
    )
    try:
        response = requests.get(url, timeout=30) # Added timeout
        response.raise_for_status() # Raise an exception for HTTP errors
        data = response.json().get("hourly", {})
        
        time_str_list = data.get("time", [])
        # Convert time strings to datetime objects
        # Open-Meteo returns ISO8601 strings like "2023-10-27T00:00"
        # These are parsed as UTC implicitly by fromisoformat if no tzinfo is present,
        # but it's better to make it explicit.
        time_dt_list = [datetime.fromisoformat(t).replace(tzinfo=timezone.utc) for t in time_str_list]
        
        precip_mm = data.get("precipitation", []) # Precipitation in mm
        temp_c = data.get("temperature_2m", [])  # Temperature in Celsius
        
        if not (len(time_dt_list) == len(precip_mm) == len(temp_c)):
            logger.warning(f"Data length mismatch for ({lat},{lon}). Times: {len(time_dt_list)}, Precip: {len(precip_mm)}, Temp: {len(temp_c)}")
            # Attempt to truncate to the shortest length if there's a mismatch and some data exists
            min_len = min(len(time_dt_list), len(precip_mm), len(temp_c))
            if min_len > 0 :
                 return precip_mm[:min_len], temp_c[:min_len], time_dt_list[:min_len]
            return [], [], []

        return precip_mm, temp_c, time_dt_list
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching weather for ({lat},{lon}) between {start_date_str}-{end_date_str}: {e}")
        return [], [], [] # Return empty lists on error

def calculate_hourly_precip_driver(precip_hourly_mm: list, p_weight: float, coeff: float) -> list:
    """Calculates hourly precipitation driver."""
    # Assuming precipitation is in mm, direct multiplication for driver value
    return [(p_val * p_weight * coeff) if p_val is not None else 0.0 for p_val in precip_hourly_mm]

def calculate_hourly_snowmelt_driver(temp_hourly_c: list, s_weight: float, coeff: float, thresh_temp: float) -> list:
    """Calculates hourly snowmelt driver."""
    # Snowmelt occurs if temperature > threshold
    return [
        (max(0, (t_val - thresh_temp)) * s_weight * coeff) if t_val is not None else 0.0
        for t_val in temp_hourly_c
    ]

def apply_rolling_average(values: list, window: int) -> list:
    """Applies a rolling average, forward-fills initial NaNs using first valid average."""
    if not values or window <= 0:
        return values
    
    rolled_values = [None] * len(values)
    current_sum = 0.0
    current_count = 0
    
    # Calculate rolling average
    for i in range(len(values)):
        current_sum += values[i]
        current_count += 1
        if i >= window:
            current_sum -= values[i - window]
            current_count -=1 # Should be current_sum -= values[i - window]
        
        if current_count > 0 and i >= window -1 : # Start recording averages once window is full
             rolled_values[i] = current_sum / current_count
    
    # Forward fill None values at the beginning with the first valid computed average
    first_valid_avg = None
    for val in rolled_values:
        if val is not None:
            first_valid_avg = val
            break
    
    if first_valid_avg is not None:
        for i in range(len(rolled_values)):
            if rolled_values[i] is None:
                rolled_values[i] = first_valid_avg
            else: # Optimization: once we hit non-None, subsequent ones are also non-None or handled
                break 
                
    # If all were None (e.g. short series or all zero inputs), fill with 0.0
    if first_valid_avg is None:
        rolled_values = [0.0] * len(values)

    return rolled_values


def fill_trailing_nones_with_last_value(values: list) -> list:
    """Fills None values at the end of the list with the last non-None value."""
    filled_values = list(values) # Create a mutable copy
    last_valid_value = None
    for i in range(len(filled_values)):
        if filled_values[i] is not None:
            last_valid_value = filled_values[i]
        elif last_valid_value is not None: # If current is None but we have a last_valid_value
            filled_values[i] = last_valid_value
    return filled_values


def run_inflow_forecast(dam_id: int, current_utc_time: datetime, forecast_horizon_hours: int = 120, lookback_days_for_meteo: int = 7) -> list[dict]:
    """
    Generates an hourly inflow forecast for a given dam.
    For V0, this is hardcoded for Grand Coulee (dam_id=1).

    Args:
        dam_id: The ID of the dam (currently ignored, uses Grand Coulee points).
        current_utc_time: The UTC timestamp when the forecast is issued.
        forecast_horizon_hours: Number of hours to forecast into the future.
        lookback_days_for_meteo: Number of past days of weather data to fetch for rolling averages etc.

    Returns:
        A list of dictionaries, each {'valid_utc': datetime, 'value_cfs': float}.
        Returns empty list on failure or if no data.
    """
    if dam_id != 1:
        logger.warning(f"inflow_model_v0 is currently hardcoded for dam_id=1 (Grand Coulee). Requested dam_id: {dam_id}")
        # For now, we'll proceed as if it's for dam_id 1, or you could return empty.
    
    # Ensure current_utc_time is timezone-aware (UTC)
    if current_utc_time.tzinfo is None:
        current_utc_time = current_utc_time.replace(tzinfo=timezone.utc)
    else:
        current_utc_time = current_utc_time.astimezone(timezone.utc)

    # Define the period for weather data fetching
    # We need past data for rolling averages and future data for the forecast.
    meteo_start_date = current_utc_time - timedelta(days=lookback_days_for_meteo)
    # Forecast ends N hours from the *start* of the current hour, or a defined point.
    # Let's make forecast start from the next full hour after current_utc_time
    forecast_start_anchor = (current_utc_time + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    meteo_end_date = forecast_start_anchor + timedelta(hours=forecast_horizon_hours -1) # -1 because OpenMeteo end_date is inclusive

    meteo_start_date_str = meteo_start_date.strftime('%Y-%m-%d')
    meteo_end_date_str = meteo_end_date.strftime('%Y-%m-%d')
    
    logger.info(f"Running inflow forecast for dam_id {dam_id}. Issue time: {current_utc_time.isoformat()}")
    logger.info(f"Weather data fetch period: {meteo_start_date_str} to {meteo_end_date_str}")
    logger.info(f"Forecast horizon: {forecast_horizon_hours} hours from {forecast_start_anchor.isoformat()}")

    # Initialize a dictionary to sum up drivers for each hourly timestamp
    # The keys will be datetime objects (hourly timestamps from Open-Meteo)
    combined_precip_drivers = {}
    combined_snowmelt_drivers = {}
    all_hourly_timestamps = set() # To keep track of all unique timestamps

    for point_config in GRAND_COULEE_POINTS:
        precip_hourly_mm, temp_hourly_c, time_hourly_dt = fetch_hourly_weather(
            point_config["lat"], point_config["lon"], meteo_start_date_str, meteo_end_date_str
        )

        if not time_hourly_dt: # Skip if no weather data for this point
            logger.warning(f"No weather data for point {point_config['name']}. Skipping.")
            continue
            
        for ts in time_hourly_dt:
            all_hourly_timestamps.add(ts)

        # Calculate raw drivers
        p_driver_hourly = calculate_hourly_precip_driver(precip_hourly_mm, point_config["p_weight"], RUNOFF_COEFF)
        s_driver_hourly_raw = calculate_hourly_snowmelt_driver(temp_hourly_c, point_config["s_weight"], SNOWMELT_COEFF, SNOWMELT_THRESH_TEMP_C)
        
        # Apply rolling average to snowmelt driver
        s_driver_hourly_rolled = apply_rolling_average(s_driver_hourly_raw, HOURLY_ROLLING_AVG_WINDOW_SNOWMELT)
        s_driver_hourly_filled = fill_trailing_nones_with_last_value(s_driver_hourly_rolled) # Fill any trailing NaNs after rolling avg

        # Apply lag (in hours)
        lag_hours = point_config["lag_days"] * 24
        
        for i, original_ts in enumerate(time_hourly_dt):
            # Calculate lagged timestamp
            # Lagging means delaying the effect. So, weather at original_ts affects inflow at lagged_ts.
            lagged_ts = original_ts + timedelta(hours=lag_hours)
            
            # Integer and fractional part of lag for potential interpolation (simplified here: take closest hour)
            # For simplicity in V0, we assign the entire driver to the closest floored hour of lagged_ts.
            # A more complex model might interpolate between hours.
            effective_ts = lagged_ts.replace(minute=0, second=0, microsecond=0) # Assign to the start of the hour

            if p_driver_hourly[i] is not None:
                combined_precip_drivers[effective_ts] = combined_precip_drivers.get(effective_ts, 0.0) + p_driver_hourly[i]
            if s_driver_hourly_filled[i] is not None: # Use the processed snowmelt driver
                combined_snowmelt_drivers[effective_ts] = combined_snowmelt_drivers.get(effective_ts, 0.0) + s_driver_hourly_filled[i]

    if not combined_precip_drivers and not combined_snowmelt_drivers:
        logger.warning("No driver data was computed. Returning empty forecast.")
        return []

    # Prepare final forecast list
    forecast_results = []
    
    # Create a sorted list of unique timestamps that we might have data for after lagging
    # and that fall within our desired forecast window.
    # The actual forecast starts from forecast_start_anchor for forecast_horizon_hours.
    
    target_forecast_timestamps = [forecast_start_anchor + timedelta(hours=h) for h in range(forecast_horizon_hours)]

    for ts in target_forecast_timestamps:
        pd_val = combined_precip_drivers.get(ts, 0.0)
        sd_val = combined_snowmelt_drivers.get(ts, 0.0)
        
        total_driver = pd_val + sd_val
        
        # Apply scaling factor and convert kcfs to cfs (original script implies output is kcfs)
        # If the drivers are already in a flow-equivalent unit, this might change.
        # Assuming 'combined' is proportional to kcfs as per original script context.
        projected_inflow_cfs = total_driver * SCALING_FACTOR * 1000.0 # kcfs to cfs
        
        forecast_results.append({
            "valid_utc": ts, # ts is already a UTC datetime object
            "value_cfs": projected_inflow_cfs if projected_inflow_cfs is not None else 0.0
            # Add 'status' or other metadata if needed later
        })
        
    logger.info(f"Generated {len(forecast_results)} hourly forecast points.")
    return forecast_results