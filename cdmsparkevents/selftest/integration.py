"""
Runs an integration test using the same interface as standard importers.
"""

from delta.tables import DeltaTable
import logging
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, IntegerType, StructField, StringType
from typing import Protocol, Any


class GetSpark(Protocol):
    """
    Typing for a function that provides a spark session.
    """
    def __call__(self, *, executor_cores: int | None = ...) -> SparkSession:
        """
        Create a spark session.
        
        executor_cores - the number of cores per Spark executor.
        """
        ...


_DB_NAME = "cdm_events_live_integration_test_db_obfuscate_ijphuihjpo"
_TABLE_NAME = "employees"
_FULL_TABLE_NAME = f'{_DB_NAME}.{_TABLE_NAME}'
_SCHEMA = StructType([
   StructField("employee_id", IntegerType(), nullable=False),
   StructField("employee_name", StringType(), nullable=False)
])


def run_import(get_spark: GetSpark, job_info: dict[str, Any], metadata: dict[str, Any]):
    """
    Run the import code.
    
    get_spark - a function to get a spark session. The arguments are:
        executor_cores - an optional argument defining the number of cores to use per Spark
            executor. The default is 1.
    job_info - a dict containing information about the job that was run that produced the
        data to import. NOTE - for this integration test the contents are not the same
        as for a CTS job event.
    metadata - a dict containing metadata about the importer from the importer's yaml file.
        NOTE -for the integration test this is empty.
    """
    # TODO DOCS documentation on the contents of job_info
    logr = logging.getLogger(__name__)
    logr.info("Running integration test", extra={"job_info": job_info})
    data = job_info["input_data"]
    mode = job_info.get("mode", "update")
    
    spark = get_spark()
    spark.sql(f"CREATE DATABASE IF NOT EXISTS {_DB_NAME}")
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {_FULL_TABLE_NAME} (
            employee_id INT,
            employee_name STRING
        )
        USING DELTA
        """
    )

    delta_table = DeltaTable.forName(spark, _FULL_TABLE_NAME)
    
    # Alias for merge
    target = "target"
    source = "source"
    
    merge_condition = f"{target}.employee_id = {source}.employee_id"
    
    df = spark.createDataFrame(data, schema=_SCHEMA)
    
    preex = delta_table.alias(
        target
        ).merge(source=df.alias(source), condition=merge_condition
        ).whenNotMatchedInsertAll(
    )
    if mode == "update":
        preex = preex.whenMatchedUpdateAll()
    preex.execute()
    
    current_table_df = spark.sql(f"SELECT * FROM {_FULL_TABLE_NAME}")
    logr.info(
        "Completed integration test. Current table contents:\n"
        + f"{current_table_df.toPandas().to_string()}"
    )
