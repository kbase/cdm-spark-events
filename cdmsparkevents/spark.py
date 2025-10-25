"""
Set up a spark session for use by importers.
"""

from functools import lru_cache
import logging
from pathlib import Path
from pyspark.conf import SparkConf
from pyspark.sql import SparkSession

from cdmsparkevents.arg_checkers import check_num as _check_num, require_string as _require_string
from cdmsparkevents.config import Config


_REQUIRED_JAR_PREFIXES = ["delta-spark_", "hadoop-aws-"]


@lru_cache
def _find_jars(cfg: Config):
    logr = logging.getLogger(__name__)
    directory = Path(cfg.spark_jars_dir).resolve()
    if not directory.is_dir():
        raise ValueError(f"Provided spark jars path is not a directory: {directory}")
    
    results = []

    for prefix in _REQUIRED_JAR_PREFIXES:
        matches = list(directory.glob(f"{prefix}*.jar"))
        if len(matches) != 1:
            raise ValueError(
                f"Expected exactly one JAR for prefix '{prefix}', found {len(matches)}"
            )
        jar = str(matches[0].resolve())
        logr.info(f"Found jar {jar}")
        results.append(jar)
    
    return ", ".join(results)


def spark_session(
        cfg: Config,
        user: str,
        app_name: str,
        executor_cores: int = 1,
    ) -> SparkSession:
    """
    Generate a spark session for an importer.
    
    cfg - The event processor configuration.
    user - the username of the KBase user. Used to determine the SQL warehouse where the data
        will be written.
    app_name - The name for the spark application. This should be unique among applications.
    executor_cores - the number of cores to use per executor.
    """
    # Sourced from https://github.com/kbase/cdm-jupyterhub/blob/main/src/spark/utils.py
    # with fairly massive changes
    _require_string(user, "user")
    config = {
        # Basic config
        "spark.app.name": _require_string(app_name, "app_name"),
        # Overrides base image configuration
        "spark.executor.cores": f"{_check_num(executor_cores, 'executor_cores')}",
        "spark.driver.host": cfg.spark_driver_host,
        "spark.master": cfg.spark_master_url,
        "spark.jars": _find_jars(cfg),
        
        # Dynamic allocation is set up in the base image setup.sh script

        # S3 setup
        "spark.hadoop.fs.s3a.endpoint": cfg.minio_url,
        "spark.hadoop.fs.s3a.access.key": cfg.minio_access_key,
        "spark.hadoop.fs.s3a.secret.key": cfg.minio_secret_key,
        "spark.hadoop.fs.s3a.path.style.access": "true",
        "spark.hadoop.fs.s3a.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",
    
        # Deltalake setup
        "spark.sql.extensions": "io.delta.sql.DeltaSparkSessionExtension",
        "spark.sql.catalog.spark_catalog": "org.apache.spark.sql.delta.catalog.DeltaCatalog",
        "spark.databricks.delta.retentionDurationCheck.enabled": "false",
        "spark.sql.catalogImplementation": "hive",
        "spark.sql.warehouse.dir": f"{cfg.spark_sql_user_warehouse_prefix.rstrip('/')}/{user}/",
        
        # Hive config is set up in the base image
    }
    
    spark_conf = SparkConf().setAll(list(config.items()))

    # Initialize SparkSession
    spark = SparkSession.builder.config(conf=spark_conf).getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    return spark
