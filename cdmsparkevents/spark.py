"""
Set up a spark session for use by importers.
"""

from functools import lru_cache
import logging
from pathlib import Path

from pyspark.conf import SparkConf
from pyspark.sql import SparkSession

from cdmsparkevents.arg_checkers import (
    check_num as _check_num,
    require_string as _require_string,
)
from cdmsparkevents.config import Config


_ICEBERG_CATALOG_ALIAS = "my"
_REQUIRED_JAR_PREFIXES = ["iceberg-spark-runtime-", "hadoop-aws-"]


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


def _personal_catalog_name(cfg: Config, user: str) -> str:
    try:
        catalog_name = cfg.polaris_personal_catalog_template.format(user=user)
    except KeyError as err:
        raise ValueError(
            "CSEP_POLARIS_PERSONAL_CATALOG_TEMPLATE may only use the {user} placeholder"
        ) from err
    if catalog_name == cfg.polaris_personal_catalog_template:
        raise ValueError("CSEP_POLARIS_PERSONAL_CATALOG_TEMPLATE must contain {user}")
    return _require_string(catalog_name, "polaris_personal_catalog")


def _get_personal_catalog_aliases(personal_catalog: str) -> list[str]:
    """Spark client aliases for the per-user Polaris catalog.

    Always includes the default `my` alias plus a portable `<username>` alias
    derived by stripping the `user_` prefix from the configured catalog name.
    Both aliases point at the same Polaris warehouse — the duplicate just gives
    importers the option of writing `my.namespace.table` or
    `<username>.namespace.table`.

    Assumes `personal_catalog` is already a valid Spark catalog identifier
    (lowercase letters, digits, underscores). With the default
    `polaris_personal_catalog_template = "user_{user}"` and KBase's username
    regex (`^[a-z][a-z0-9_]*$`), this is guaranteed.
    """
    aliases = [_ICEBERG_CATALOG_ALIAS]
    portable_alias = personal_catalog.strip()
    if portable_alias.startswith("user_"):
        portable_alias = portable_alias[len("user_"):]
    if portable_alias and portable_alias not in aliases:
        aliases.append(portable_alias)
    return aliases


def _s3_endpoint_for_iceberg(cfg: Config) -> str:
    endpoint = cfg.minio_url
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        return endpoint
    protocol = "https" if cfg.minio_secure else "http"
    return f"{protocol}://{endpoint}"


def _s3_secure(cfg: Config) -> bool:
    if cfg.minio_url.startswith("https://"):
        return True
    if cfg.minio_url.startswith("http://"):
        return False
    return cfg.minio_secure


def _get_catalog_conf(cfg: Config, user: str) -> dict[str, str]:
    polaris_uri = cfg.polaris_catalog_uri.rstrip("/")
    personal_catalog = _personal_catalog_name(cfg, user)
    s3_props = {
        "s3.endpoint": _s3_endpoint_for_iceberg(cfg),
        "s3.access-key-id": cfg.minio_access_key,
        "s3.secret-access-key": cfg.minio_secret_key,
        "s3.path-style-access": "true",
        "s3.region": "us-east-1",
    }

    def _catalog_props(prefix: str) -> dict[str, str]:
        props = {
            f"{prefix}": "org.apache.iceberg.spark.SparkCatalog",
            f"{prefix}.type": "rest",
            f"{prefix}.uri": polaris_uri,
            f"{prefix}.credential": cfg.polaris_credential,
            f"{prefix}.warehouse": personal_catalog,
            f"{prefix}.scope": "PRINCIPAL_ROLE:ALL",
            f"{prefix}.token-refresh-enabled": "true",
            f"{prefix}.client.region": "us-east-1",
        }
        for key, value in s3_props.items():
            props[f"{prefix}.{key}"] = value
        return props

    config = {}
    for catalog_alias in _get_personal_catalog_aliases(personal_catalog):
        config.update(_catalog_props(f"spark.sql.catalog.{catalog_alias}"))
    return config


def generate_spark_conf(
    cfg: Config,
    user: str,
    app_name: str,
    executor_cores: int = 1,
) -> dict[str, str]:
    """
    Generate the Spark configuration used by the event processor.

    Wires the per-user Iceberg catalog (Polaris REST) under the default
    `my` alias plus a portable `<sanitized-user>` alias, configures S3
    access for both Spark's Hadoop client and Iceberg's S3FileIO, and
    sets the dynamic-allocation / shuffle defaults the importer code paths
    rely on.

    cfg - the event processor configuration. Must have a non-empty Polaris
        catalog URI, OAuth credential, and S3 endpoint; see
        :class:`cdmsparkevents.config.Config`.
    user - the KBase username. Resolved through
        ``cfg.polaris_personal_catalog_template`` (default ``user_{user}``)
        to select the per-user Polaris warehouse.
    app_name - the Spark application name. Should be unique among
        applications running against the same Spark master.
    executor_cores - cores per Spark executor. Defaults to 1 since most
        importer work is IO-bound.

    Returns the Spark config as a flat ``{key: value}`` dict suitable for
    ``SparkConf().setAll(...)``. Split out from :func:`spark_session` to
    make the conf assertable in unit tests without spinning up Spark.
    """
    _require_string(user, "user")
    config = {
        # Basic config
        "spark.app.name": _require_string(app_name, "app_name"),
        # Overrides base image configuration
        "spark.driver.host": cfg.spark_driver_host,
        "spark.master": cfg.spark_master_url,
        "spark.jars": _find_jars(cfg),
        # Resources. The event processor primarily loads imported data into Iceberg.
        # Leave some fields as default for now, alter / config as needed
        # "spark.driver.memory": # default
        # "spark.driver.cores": # default
        # "spark.executor.memory": # default
        "spark.executor.cores": f"{_check_num(executor_cores, 'executor_cores')}",
        "spark.dynamicAllocation.enabled": "true",
        "spark.dynamicAllocation.maxExecutors": "5",  # default from old cdm-spark-standalone
        # shuffle tracking shouldn't be used with decommissioning (below)
        "spark.dynamicAllocation.shuffleTracking.enabled": "false",
        # Backlog timeouts for scaling up
        "spark.dynamicAllocation.schedulerBacklogTimeout": "1s",  # Fast initial scale-up
        "spark.dynamicAllocation.sustainedSchedulerBacklogTimeout": "10s",  # Conservative follow-up
        # Executor idle timeouts for scaling down
        "spark.dynamicAllocation.executorIdleTimeout": "300s",
        "spark.dynamicAllocation.cachedExecutorIdleTimeout": "1800s",
        # S3 setup for importer inputs and any direct s3a:// reads.
        "spark.hadoop.fs.s3a.endpoint": cfg.minio_url,
        "spark.hadoop.fs.s3a.access.key": cfg.minio_access_key,
        "spark.hadoop.fs.s3a.secret.key": cfg.minio_secret_key,
        "spark.hadoop.fs.s3a.connection.ssl.enabled": str(_s3_secure(cfg)).lower(),
        "spark.hadoop.fs.s3a.path.style.access": "true",
        "spark.hadoop.fs.s3a.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",
        # Iceberg / Polaris setup. The default catalog keeps existing importer code
        # that writes namespace.table identifiers on the Iceberg path.
        "spark.sql.extensions": "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        "spark.sql.defaultCatalog": _ICEBERG_CATALOG_ALIAS,
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
    config.update(_get_catalog_conf(cfg, user))
    return config


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
    config = generate_spark_conf(cfg, user, app_name, executor_cores=executor_cores)

    spark_conf = SparkConf().setAll(list(config.items()))

    # Initialize SparkSession
    spark = SparkSession.builder.config(conf=spark_conf).getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    return spark
