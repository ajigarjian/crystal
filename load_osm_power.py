"""
Load OSM wind generators & plants from a single GeoJSON
into dim_plants / dim_generators tables.

  • Tested with Postgres 15 + PostGIS 3.x
  • Requires shapely, psycopg2-binary
"""

import json, os, re, sys, psycopg2, io
from shapely.geometry import shape
from shapely import wkb

# Optional: Load environment variables from a .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ───── 1. CONFIG ───────────────────────────────────────────────
GEOJSON_PATH = "export_combustion.geojson"          # <-- path to your file
PG_HOST      = os.getenv("DB_HOST", "127.0.0.1")
PG_PORT      = int(os.getenv("DB_PORT", 1234))
PG_DB        = os.getenv("DB_NAME", "crystal")
PG_USER      = os.getenv("DB_USER", "postgres")
PG_PW        = os.getenv("DB_PASSWORD", r'A>\$icV~t||V7RT-')  # set in your shell or .env
SRID         = 4326
# ────────────────────────────────────────────────────────────────

def to_wkb(geom):
    return wkb.dumps(geom, hex=False, srid=SRID)

def to_wkb_hex(geom):
    """Convert geometry to hexadecimal WKB string that PostGIS can parse"""
    return wkb.dumps(geom, hex=True, srid=SRID)

def parse_output_mw(text):
    if not text:
        return None
    m = re.search(r"([\d.]+)", text)
    return float(m.group(1)) if m else None

def main():
    if PG_PW is None:
        sys.exit("❌  Set DB_PASSWORD env var first")

    try:
        conn = psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            dbname=PG_DB,
            user=PG_USER,
            password=PG_PW
        )
    except Exception as e:
        sys.exit(f"❌  Could not connect to database: {e}")

    conn.autocommit = True
    cur = conn.cursor()

    # ── 2. CREATE TABLES IF NOT EXISTS ─────────────────────────
    cur.execute("""
    CREATE EXTENSION IF NOT EXISTS postgis;

    CREATE TABLE IF NOT EXISTS dim_plants (
        plant_id            text PRIMARY KEY,
        name                text,
        alt_name            text,
        operator            text,
        power               text,
        plant_source        text,
        plant_method        text,
        output_electricity  text,
        start_date          text,
        ref_us_eia          text,
        wikidata            text,
        wikipedia           text,
        source_tag          text,
        type_tag            text,
        geom                geometry
    );

    CREATE TABLE IF NOT EXISTS dim_generators (
        generator_id            text PRIMARY KEY,
        plant_id                text,
        generator_source        text,
        generator_method        text,
        generator_type          text,
        output_electricity      text,
        manufacturer            text,
        manufacturer_type       text,
        model                   text,
        operator                text,
        wikidata                text,
        start_date              text,
        power                   text,
        size_tag                text,
        geom                    geometry
    );
    """)

    # ── 3. LOAD & SPLIT GEOJSON ────────────────────────────────
    with open(GEOJSON_PATH) as f:
        gj = json.load(f)

    rows_plants, rows_gens = [], []

    for feat in gj["features"]:
        props = feat.get("properties", {})
        geom  = shape(feat["geometry"])
        geom_wkb_hex = to_wkb_hex(geom)

        if props.get("power") == "plant":
            rows_plants.append((
                props["@id"],
                props.get("name"),
                props.get("alt_name"),
                props.get("operator"),
                props.get("power"),
                props.get("plant:source") or props.get("generator:source"),
                props.get("plant:method"),
                props.get("plant:output:electricity"),
                props.get("start_date"),
                props.get("ref:US:EIA"),
                props.get("wikidata"),
                props.get("wikipedia"),
                props.get("source"),
                props.get("type"),
                geom_wkb_hex
            ))

        elif props.get("power") == "generator":
            # grab parent relation (first one) if exists
            rels = props.get("relations", [])
            plant_rel = rels[0]["rel"] if rels else None

            rows_gens.append((
                props["@id"],
                plant_rel,
                props.get("generator:source"),
                props.get("generator:method"),
                props.get("generator:type"),
                props.get("generator:output:electricity"),
                props.get("manufacturer"),
                props.get("manufacturer:type"),
                props.get("model"),
                props.get("operator"),
                props.get("wikidata"),
                props.get("start_date"),
                props.get("power"),
                props.get("size"),
                geom_wkb_hex
            ))

    print(f"→ Parsed {len(rows_plants)} plants and {len(rows_gens)} generators")

    # ── 4. COPY-INSERT (fast) ──────────────────────────────────
    with conn, conn.cursor() as c:

        # Plants
        if rows_plants:
            buf = io.StringIO()
            for row in rows_plants:
                buf.write('\t'.join("" if v is None else str(v) for v in row) + '\n')
            buf.seek(0)
            c.copy_expert("""
              COPY dim_plants (
                plant_id,name,alt_name,operator,power,
                plant_source,plant_method,output_electricity,start_date,
                ref_us_eia,wikidata,wikipedia,source,type,geom
              )
              FROM STDIN WITH (FORMAT csv, DELIMITER E'\t', NULL '')
            """, buf)

        # Generators
        if rows_gens:
            buf = io.StringIO()
            for row in rows_gens:
                buf.write('\t'.join("" if v is None else str(v) for v in row) + '\n')
            buf.seek(0)
            c.copy_expert("""
              COPY dim_generators (
                generator_id,plant_id,generator_source,generator_method,
                generator_type,output_electricity,manufacturer,manufacturer_type,
                model,operator,wikidata,start_date,power,size,geom
              )
              FROM STDIN WITH (FORMAT csv, DELIMITER E'\t', NULL '')
            """, buf)

    print("✅  Load complete.")
    cur.close(); conn.close()

if __name__ == "__main__":
    main()
