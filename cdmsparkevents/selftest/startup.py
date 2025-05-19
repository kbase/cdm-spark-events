"""
Run a basic self test on startup of the event loop. This can take seconds to minutes.
"""

import logging
from pyspark.sql.types import StructType, IntegerType, StructField, StringType, Row
import uuid

from cdmsparkevents.config import Config
from cdmsparkevents.spark import spark_session


def run_deltalake_startup_test(cfg: Config):
    """
    Runs a simple check that the service can write to and read from deltalake tables:
    
    * Creates a DB with a unique name
    * Writes a very small amount of data to an employees table
    * Queries the table
    * Drops the DB
    
    cfg - The event processor configuration.
    """
    logr = logging.getLogger(__name__)
    if not cfg.minio_startup_deltalake_self_test_bucket:
        raise ValueError("A startup test bucket must be provided in the configuration")
    name = "cdm_events_startup_test_" + str(uuid.uuid4()).replace("-", "_")
    schema = StructType([
       StructField("employee_id", IntegerType(), nullable=False),
       StructField("employee_name", StringType(), nullable=False)
    ])
    data = [
        (1, "Alice"),
        (2, "Bob")
    ]
    expected_data = [
        Row(employee_id=1, employee_name="Alice"),
        Row(employee_id=2, employee_name="Bob")
    ]
    spark = spark_session(
        cfg,
        name,
        delta_tables_s3_path=f"{cfg.minio_startup_deltalake_self_test_bucket}/cdm_events_self_test"
    )
    df = spark.createDataFrame(data, schema=schema)
    logr.info(f"Creating self test database {name}")
    spark.sql(f"CREATE DATABASE {name}")
    try:
        logr.info("Writing to self test database")
        df.write.mode(
            "overwrite"
            ).option("compression", "snappy"
            ).format("delta"
            ).saveAsTable(f"{name}.employees"
        )
        logr.info("Querying self test database")
        newdf = spark.sql(f"SELECT * FROM {name}.employees")
        actual_data = newdf.orderBy("employee_id").collect()
        if expected_data != actual_data:
            raise ValueError(f"""The startup self test failed. Expected data:
                {expected_data}
                Actual data:
                {actual_data}
                """
            )
    finally:
        logr.info(f"Dropping self test database {name}")
        spark.sql(f"DROP DATABASE {name} CASCADE")
    logr.info("Deltalake connectivity startup self test passed")
