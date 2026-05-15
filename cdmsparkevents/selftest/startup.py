"""
Run a basic self test on startup of the event loop. This can take seconds to minutes.
"""

import logging
import uuid

from pyspark.sql.types import IntegerType, Row, StringType, StructField, StructType

from cdmsparkevents.config import Config
from cdmsparkevents.spark import spark_session


def run_iceberg_startup_test(cfg: Config):
    """
    Runs a simple check that the service can write to and read from Iceberg tables:

    * Creates a namespace with a unique name
    * Writes a very small amount of data to an employees table
    * Queries the table
    * Drops the namespace

    cfg - The event processor configuration.
    """
    logr = logging.getLogger(__name__)
    name = "cdm_events_startup_test_" + str(uuid.uuid4()).replace("-", "_")
    schema = StructType(
        [
            StructField("employee_id", IntegerType(), nullable=False),
            StructField("employee_name", StringType(), nullable=False),
        ]
    )
    data = [(1, "Alice"), (2, "Bob")]
    expected_data = [
        Row(employee_id=1, employee_name="Alice"),
        Row(employee_id=2, employee_name="Bob"),
    ]
    table_name = f"{name}.employees"
    spark = spark_session(cfg, "event_processor_startup_test", name)
    try:
        df = spark.createDataFrame(data, schema=schema)
        logr.info(f"Creating self test namespace {name}")
        spark.sql(f"CREATE NAMESPACE {name}")
        try:
            logr.info("Writing to self test namespace")
            df.writeTo(table_name).using("iceberg").create()
            logr.info("Querying self test namespace")
            newdf = spark.sql(f"SELECT * FROM {table_name}")
            actual_data = newdf.orderBy("employee_id").collect()
            if expected_data != actual_data:
                raise ValueError(f"""The startup self test failed. Expected data:
                    {expected_data}
                    Actual data:
                    {actual_data}
                    """)
        finally:
            # PURGE removes the table's data + metadata files from S3 as well
            # as dropping the catalog entry; otherwise repeated selftest runs
            # would accumulate orphaned files under the warehouse prefix.
            # `DROP NAMESPACE … CASCADE` isn't supported by Polaris (returns
            # NamespaceNotEmptyException), so the table is dropped explicitly
            # first and the namespace second.
            logr.info(f"Dropping self test table {table_name}")
            spark.sql(f"DROP TABLE IF EXISTS {table_name} PURGE")
            logr.info(f"Dropping self test namespace {name}")
            spark.sql(f"DROP NAMESPACE IF EXISTS {name}")
    finally:
        spark.stop()
    logr.info("Iceberg connectivity startup self test passed")
