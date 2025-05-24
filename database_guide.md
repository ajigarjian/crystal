# Hydro-Data Warehouse – Table Guide  
*(dim & fact layer for dam operations + forecasting)*

---

## 1. `dim_dam`

| Column (core)        | Description                                            | Example                |
|----------------------|--------------------------------------------------------|------------------------|
| `dam_id` **PK**      | Surrogate key                                          | `3`                    |
| `dam_name`           | Human-friendly                                         | “Rocky Reach Dam”      |
| `dam_code`           | 3-char USACE / CWMS code                               | `RRH`                  |
| `river`, `state`     | Context                                               | Columbia, WA           |
| `latitude`, `longitude` | WGS-84                                              | 47.5334, –120.2955     |
| `storage_max_acft`   | Max pool storage (ac-ft)                               | 593 000                |
| … more attributes    | owner, operator, capacity, year_completed, etc.        |                        |

*Purpose:* master reference for every other fact table.

---

## 2. `dim_metric`

| Column          | Description                          | Example |
|-----------------|--------------------------------------|---------|
| `metric_id` **PK** | Surrogate key                    | `6`     |
| `metric_name`   | Short id                             | `inflow_cfs` |
| `units`         | Canonical units                      | `cfs`   |

*Purpose:* single lookup row for each physical quantity.

---

## 3. `dim_source`

| Column             | Description                        | Example            |
|--------------------|------------------------------------|--------------------|
| `source_id` **PK** | Surrogate key                      | `2`                |
| `source_name`      | “USACE-CWMS”, “USGS-NWIS”, “Derived”… | `USACE-CWMS`    |
| `latency_minutes`  | Typical delay vs real time         | `45`               |

*Purpose:* provenance / lineage & quality scoring.

---

## 4. `dim_model`

| Column            | Description                                   | Example               |
|-------------------|-----------------------------------------------|-----------------------|
| `model_id` **PK** | Surrogate key                                 | `7`                   |
| `model_name`      | Friendly tag                                  | `GC_AI_Lite`          |
| `version_tag`     | SemVer / git SHA                              | `v1.3.2`              |
| `author`          | Owner / contact                               | `data-team`           |
| `description`     | Free-text                                     |                       |

*Purpose:* lets multiple forecast engines/version live side-by-side.

---

## 5. `fact_dam_ops`  — **observed values**

| Column set (minimal)                  | Notes                                          |
|---------------------------------------|------------------------------------------------|
| `ts_utc` (timestamp)                  | Observation time (UTC)                         |
| `dam_id` FK → `dim_dam`               |                                                |
| `metric_id` FK → `dim_metric`         |                                                |
| `source_id` FK → `dim_source`         |                                                |
| `value_num`                           | Numeric value                                  |
| `quality` (`R`aw / `D`erived / `E`st) |                                                |
| PK                                    | `(ts_utc, dam_id, metric_id)`                  |

*Purpose:* ground-truth data stream (forebay, inflow, spill …).  
Usually hourly; some (e.g. USGS daily) at coarser step.

---

## 6. `fact_forecast_run`  — **forecast header**

| Column                   | Description                                     |
|--------------------------|-------------------------------------------------|
| `run_id` **PK**          | Auto‐inc.                                       |
| `model_id` FK            | Which model/version produced this run           |
| `run_issued_utc`         | Timestamp model finished                        |
| `forecast_start_utc`     | First valid time of any forecast in the batch   |
| `forecast_end_utc`       | Last valid time                                 |
| `horizon_hours`          | Convenience denormalisation                     |
| `lead_time_hours`        | `forecast_start – run_issued`                   |
| `note` JSONB             | Free meta (git hash, hyper-params, …)           |

Think of this as the folder label for a forecast drop.

---

## 7. `fact_dam_forecast`  — **forecast values**

| Column                                   | Notes                                          |
|------------------------------------------|------------------------------------------------|
| `run_id` FK → `fact_forecast_run`        | Parent run                                     |
| `ensemble_member` *INT*                  | –1 = deterministic, 0–N otherwise             |
| `dam_id` FK → `dim_dam`                  |                                                |
| `metric_id` FK → `dim_metric`            | Usually `6` for inflow                         |
| `valid_utc`                              | Target time this value applies to              |
| `value_cfs` (or `_num`)                  | Forecast number                                |
| `created_at`                             | Ingestion timestamp                            |
| **PK**                                   | `(run_id, ensemble_member, dam_id, valid_utc)` |

Stores everything from a single deterministic line to a 50-member ensemble.

---

## Workflow Example (single dam, 5-member ensemble)

1. **Run issued** → insert row into `fact_forecast_run`, get `run_id = 20421`.
2. **Write forecasts** → 5 × 181 h = 905 rows into `fact_dam_forecast`
   (`ensemble_member = 0-4`, `valid_utc = +1 h … +181 h`).
3. **Observations stream** → upsert into `fact_dam_ops`.
4. **Verification query**  

   ```sql
   SELECT f.valid_utc,
          f.value_cfs  AS fcst,
          o.value_num  AS obs,
          f.value_cfs - o.value_num AS delta
   FROM   fact_dam_forecast f
   LEFT   JOIN fact_dam_ops o
          ON (f.dam_id     = o.dam_id
          AND f.metric_id  = o.metric_id
          AND f.valid_utc  = o.ts_utc)
   WHERE  f.run_id = 20421
     AND  f.metric_id = 6;  -- inflow