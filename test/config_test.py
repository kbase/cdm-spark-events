from cdmsparkevents.config import Config


def _set_required_env(monkeypatch):
    monkeypatch.setenv("CSEP_KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    monkeypatch.setenv("CSEP_KAFKA_TOPIC_JOBS", "cts-jobs")
    monkeypatch.setenv("CSEP_KAFKA_TOPIC_JOBS_DLQ", "cts-jobs-dlq")
    monkeypatch.setenv("CSEP_KAFKA_GROUP_ID", "events")
    monkeypatch.setenv("CSEP_CDM_TASK_SERVICE_URL", "http://cts")
    monkeypatch.setenv("CSEP_CDM_TASK_SERVICE_ADMIN_TOKEN", "cts-token")
    monkeypatch.setenv("CSEP_MINIO_URL", "minio:9000")
    monkeypatch.setenv("CSEP_MINIO_ACCESS_KEY", "events")
    monkeypatch.setenv("CSEP_MINIO_SECRET_KEY", "event-secret")
    monkeypatch.setenv("CSEP_POLARIS_CATALOG_URI", "http://polaris:8181/api/catalog")
    monkeypatch.setenv("CSEP_POLARIS_CREDENTIAL", "client:secret")
    monkeypatch.setenv("CSEP_SPARK_MASTER_URL", "spark://spark-master:7077")
    monkeypatch.setenv("CSEP_SPARK_DRIVER_HOST", "cdm-events")
    monkeypatch.setenv("CSEP_SPARK_JARS_DIR", "/usr/local/spark/jars")


def test_config_accepts_iceberg_startup_self_test(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("CSEP_STARTUP_ICEBERG_SELF_TEST", "true")

    cfg = Config()

    assert cfg.startup_iceberg_self_test is True


def test_config_accepts_legacy_startup_self_test_alias(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("CSEP_STARTUP_DELTALAKE_SELF_TEST", "true")

    cfg = Config()

    assert cfg.startup_iceberg_self_test is True


def test_safe_dump_redacts_secrets(monkeypatch):
    _set_required_env(monkeypatch)

    dumped = Config().safe_dump()

    assert dumped["minio_access_key"] == "events"
    assert dumped["polaris_catalog_uri"] == "http://polaris:8181/api/catalog"
    assert dumped["minio_secret_key"] == "REDACTED BY THE MINISTRY OF TRUTH"
    assert dumped["polaris_credential"] == "REDACTED BY THE MINISTRY OF TRUTH"
