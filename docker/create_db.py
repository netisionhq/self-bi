import os
from superset.app import create_app
from dotenv import load_dotenv
load_dotenv("/app/docker/.env")

print("env host ",os.getenv("HOST"))
DATABASE_NAME = os.getenv("DATABASE_NAME", "AI Landing Zone")
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "Sales_Analyst")

HOST = os.getenv("HOST","64.227.152.66")
PORT = os.getenv("CLICKHOUSE_PORT","8123")
USERNAME = os.getenv("USERNAME","netision")
PASSWORD = os.getenv("PASSWORD","netision")

SQLALCHEMY_URI = f"clickhousedb+connect://{USERNAME}:{PASSWORD}@{HOST}:{PORT}/{CLICKHOUSE_DB}"
INCLUDE_VIEWS = False

# Maps raw ClickHouse table name -> friendly Superset dataset name
TABLE_MAPPING = {
    'areamanager': 'dim_area_manager',
    'calendar': 'dim_date',
    'calendarholiday': 'dim_holiday',
    'holiday_calender': 'ref_holiday_calendar',
    'lflcal': 'ref_like_for_like_calendar',
    'restaurant_hourly_operationskpi': 'fact_store_hourly_performance',
    'complaints_survey_hook': 'fact_customer_feedback',
    'hook_Entity': 'dim_business_entity',
    'hook_aggregators_kpi': 'fact_delivery_aggregator_performance',
    'hook_cancellation_compliance': 'fact_order_cancellation_compliance',
    'hook_complaints_kpi': 'fact_customer_complaints',
    'hook_discount_kpi': 'fact_discount_performance',
    'hook_google_rating': 'fact_google_reviews',
    'hook_otherfactor': 'fact_external_business_factors',
    'hook_socialmedia': 'fact_social_media_performance',
    'final_forecasts': 'fact_sales_forecast',
    'metadata_forecast': 'ref_forecast_model_settings',
    'metadata_revenue': 'ref_revenue_model_settings',
    'metadata_stat': 'ref_statistical_model_settings',
}


def fetch_clickhouse_tables(sqlalchemy_uri: str, ch_db: str, include_views: bool = False) -> list[str]:
    from sqlalchemy import create_engine, text

    engine = create_engine(sqlalchemy_uri)
    engine_filter = (
        ""
        if include_views
        else "AND engine NOT IN ('View', 'MaterializedView', 'LiveView')"
    )

    q = text(f"""
        SELECT name
        FROM system.tables
        WHERE database = :db
        {engine_filter}
        ORDER BY name
    """)

    with engine.connect() as conn:
        rows = conn.execute(q, {"db": ch_db}).fetchall()

    return [r[0] for r in rows]


def run_setup():
    app = create_app()

    with app.app_context():
        from superset import db
        from superset.models.core import Database
        from superset.connectors.sqla.models import SqlaTable

        # --------------------------------------------------------
        # 1. Ensure the Superset Database connection entry exists
        # --------------------------------------------------------
        database = db.session.query(Database).filter_by(database_name=DATABASE_NAME).first()
        if not database:
            print(f"[+] Creating Superset database entry: '{DATABASE_NAME}'")
            database = Database(
                database_name=DATABASE_NAME,
                sqlalchemy_uri=SQLALCHEMY_URI
            )
            db.session.add(database)
            db.session.commit()
        else:
            if (database.sqlalchemy_uri or "").strip() != SQLALCHEMY_URI.strip():
                print(f"[~] Updating SQLAlchemy URI for '{DATABASE_NAME}'")
                database.sqlalchemy_uri = SQLALCHEMY_URI
                db.session.commit()
            else:
                print(f"[=] Database entry '{DATABASE_NAME}' already up to date.")

        # --------------------------------------------------------
        # 2. Fetch all tables from ClickHouse
        # --------------------------------------------------------
        all_tables = fetch_clickhouse_tables(
            SQLALCHEMY_URI, ch_db=CLICKHOUSE_DB, include_views=INCLUDE_VIEWS
        )
        print(f"\n[i] Discovered {len(all_tables)} table(s) in ClickHouse DB '{CLICKHOUSE_DB}'.")

        # Warn about TABLE_MAPPING entries that don't exist in ClickHouse
        missing = set(TABLE_MAPPING.keys()) - set(all_tables)
        if missing:
            print(f"[!] WARNING: {len(missing)} TABLE_MAPPING source(s) not found in ClickHouse:")
            for m in sorted(missing):
                print(f"      - {m}  ->  {TABLE_MAPPING[m]}")

        # --------------------------------------------------------
        # 3. Register every discovered table as a Superset dataset
        #    Use TABLE_MAPPING friendly name if available,
        #    otherwise fall back to the raw ClickHouse table name.
        # --------------------------------------------------------
        created = skipped = failed = 0

        for raw_name in all_tables:
            # Resolve the display name: mapped name or raw name
            display_name = TABLE_MAPPING.get(raw_name, raw_name)

            try:
                # Check if a dataset already exists for this physical table
                existing = db.session.query(SqlaTable).filter_by(
                    table_name=raw_name,
                    schema=CLICKHOUSE_DB,
                    database_id=database.id,
                ).first()

                if existing:
                    print(f"[=] Skipping  '{raw_name}'  (already registered as '{existing.table_name}')")
                    skipped += 1
                    continue

                # Create the dataset, pointing at the real ClickHouse table name
                print(f"[+] Registering  '{raw_name}'  as  '{display_name}'")
                ds = SqlaTable(
                    table_name=raw_name,        # physical table in ClickHouse
                    schema=CLICKHOUSE_DB,
                )
                # Use the friendly name as the human-readable label shown in Superset UI
                ds.verbose_name = display_name
                ds.database = database

                db.session.add(ds)
                db.session.commit()

                # Pull column metadata from ClickHouse
                ds.fetch_metadata()
                db.session.commit()

                created += 1

            except Exception as e:
                db.session.rollback()
                failed += 1
                print(f"[x] FAILED for '{raw_name}': {e}")

        # --------------------------------------------------------
        # 4. Summary
        # --------------------------------------------------------
        print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Done!
  ✔ Created : {created}
  ↷ Skipped : {skipped}
  ✘ Failed  : {failed}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        """)


if __name__ == "__main__":
    run_setup()