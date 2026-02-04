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
        "spark.driver.host": cfg.spark_driver_host,
        "spark.master": cfg.spark_master_url,
        "spark.jars": _find_jars(cfg),

        # Resources. Since the event processor is just for loading data in to delta shouldn't
        # need much in the way of resources.
        # Leave some fields as default for now, alter / config as needed
        #"spark.driver.memory": # default
        #"spark.driver.cores": # default
        #"spark.executor.memory": # default
        "spark.executor.cores": f"{_check_num(executor_cores, 'executor_cores')}",
        "spark.dynamicAllocation.enabled": "true",
        "spark.dynamicAllocation.maxExecutors": "5", # default from old cdm-spark-standalone
        # shuffle tracking shouldn't be used with decommissioning (below)
        "spark.dynamicAllocation.shuffleTracking.enabled": "false",
        # Backlog timeouts for scaling up
        "spark.dynamicAllocation.schedulerBacklogTimeout": "1s",           # Fast initial scale-up
        "spark.dynamicAllocation.sustainedSchedulerBacklogTimeout": "10s", # Conservative follow-up
        # Executor idle timeouts for scaling down
        "spark.dynamicAllocation.executorIdleTimeout": "300s",
        "spark.dynamicAllocation.cachedExecutorIdleTimeout": "1800s",

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
        "spark.sql.warehouse.dir": f"{cfg.spark_sql_user_warehouse_prefix.rstrip('/')}/{user}/",
        # Delta Lake optimizations
        "spark.databricks.delta.optimizeWrite.enabled": "true",
        "spark.databricks.delta.autoCompact.enabled": "true",
        
        # Hive setup
        "spark.hive.metastore.uris": cfg.hive_metastore_url,
        "spark.sql.catalogImplementation": "hive",
        "spark.sql.hive.metastore.version": "4.0.0",
        "spark.sql.hive.metastore.jars": "path",
        # TODO CODE tighten this up at some point, but I don't know what jars are required
        "spark.sql.hive.metastore.jars.path": f"{cfg.spark_jars_dir}/*",
        
        # misc defaults
        "spark.decommission.enabled": "true",
        "spark.storage.decommission.rddBlocks.enabled": "true",
        "spark.storage.decommission.shuffleBlocks.enabled": "true",
        # Broadcast join configurations
        "spark.sql.autoBroadcastJoinThreshold": "52428800",  # 50MB (default is 10MB)
        # Shuffle and compression configurations
        "spark.reducer.maxSizeInFlight": "96m",  # 96MB (default is 48MB)
        "spark.shuffle.file.buffer": "1m",  # 1MB (default is 32KB)
    }
    
    spark_conf = SparkConf().setAll(list(config.items()))

    # Initialize SparkSession
    spark = SparkSession.builder.config(conf=spark_conf).getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    return spark
