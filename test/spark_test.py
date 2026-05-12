from cdmsparkevents.config import Config
from cdmsparkevents.spark import generate_spark_conf


def _set_required_env(
    monkeypatch, jars_dir, minio_url="minio:9000", minio_secure="false"
):
    monkeypatch.setenv("CSEP_KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    monkeypatch.setenv("CSEP_KAFKA_TOPIC_JOBS", "cts-jobs")
    monkeypatch.setenv("CSEP_KAFKA_TOPIC_JOBS_DLQ", "cts-jobs-dlq")
    monkeypatch.setenv("CSEP_KAFKA_GROUP_ID", "events")
    monkeypatch.setenv("CSEP_CDM_TASK_SERVICE_URL", "http://cts")
    monkeypatch.setenv("CSEP_CDM_TASK_SERVICE_ADMIN_TOKEN", "cts-token")
    monkeypatch.setenv("CSEP_MINIO_URL", minio_url)
    monkeypatch.setenv("CSEP_MINIO_ACCESS_KEY", "events")
    monkeypatch.setenv("CSEP_MINIO_SECRET_KEY", "event-secret")
    monkeypatch.setenv("CSEP_MINIO_SECURE", minio_secure)
    monkeypatch.setenv("CSEP_POLARIS_CATALOG_URI", "http://polaris:8181/api/catalog/")
    monkeypatch.setenv("CSEP_POLARIS_CREDENTIAL", "client:secret")
    monkeypatch.setenv("CSEP_SPARK_MASTER_URL", "spark://spark-master:7077")
    monkeypatch.setenv("CSEP_SPARK_DRIVER_HOST", "cdm-events")
    monkeypatch.setenv("CSEP_SPARK_JARS_DIR", str(jars_dir))


def _write_required_jars(jars_dir):
    (jars_dir / "iceberg-spark-runtime-4.0_2.13-1.10.1.jar").write_text("")
    (jars_dir / "hadoop-aws-3.4.1.jar").write_text("")


def test_generate_spark_conf_uses_iceberg_polaris_catalog(monkeypatch, tmp_path):
    _write_required_jars(tmp_path)
    _set_required_env(monkeypatch, tmp_path)

    conf = generate_spark_conf(Config(), "Alice-Lake", "import_app", executor_cores=2)

    assert conf["spark.sql.extensions"] == (
        "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions"
    )
    assert conf["spark.sql.defaultCatalog"] == "my"
    assert conf["spark.sql.catalog.my"] == "org.apache.iceberg.spark.SparkCatalog"
    assert conf["spark.sql.catalog.my.type"] == "rest"
    assert conf["spark.sql.catalog.my.uri"] == "http://polaris:8181/api/catalog"
    assert conf["spark.sql.catalog.my.warehouse"] == "user_Alice-Lake"
    assert conf["spark.sql.catalog.alice_lake.warehouse"] == "user_Alice-Lake"
    assert conf["spark.sql.catalog.my.s3.endpoint"] == "http://minio:9000"
    assert conf["spark.hadoop.fs.s3a.connection.ssl.enabled"] == "false"
    assert "delta" not in " ".join(conf.values()).lower()
    assert "hive" not in " ".join(conf.keys()).lower()
    assert conf["spark.executor.cores"] == "2"


def test_generate_spark_conf_uses_https_for_schemeless_secure_s3_endpoint(
    monkeypatch,
    tmp_path,
):
    _write_required_jars(tmp_path)
    _set_required_env(
        monkeypatch,
        tmp_path,
        minio_url="minio.stage.berdl.kbase.us",
        minio_secure="true",
    )

    conf = generate_spark_conf(Config(), "tgu", "import_app")

    assert (
        conf["spark.sql.catalog.my.s3.endpoint"] == "https://minio.stage.berdl.kbase.us"
    )
    assert conf["spark.hadoop.fs.s3a.connection.ssl.enabled"] == "true"


def test_generate_spark_conf_preserves_explicit_s3_endpoint_scheme(
    monkeypatch, tmp_path
):
    _write_required_jars(tmp_path)
    _set_required_env(
        monkeypatch,
        tmp_path,
        minio_url="http://minio.internal:9000",
        minio_secure="true",
    )

    conf = generate_spark_conf(Config(), "tgu", "import_app")

    assert conf["spark.sql.catalog.my.s3.endpoint"] == "http://minio.internal:9000"
    assert conf["spark.hadoop.fs.s3a.connection.ssl.enabled"] == "false"
