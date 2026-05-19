"""
Configuration for the event handler.
"""

from typing import Annotated, Any

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """
    The configuration for the CDM events processor.
    """
    model_config = SettingsConfigDict(case_sensitive=True, str_strip_whitespace=True, frozen=True)

    kafka_bootstrap_servers: Annotated[str, Field(
        validation_alias="CSEP_KAFKA_BOOTSTRAP_SERVERS",
        examples=["localhost:9092"],
        description="The comma separated bootstrap servers list for Kafka.",
        min_length=1,
    )]
    kafka_topic_jobs: Annotated[str,  Field(
        validation_alias="CSEP_KAFKA_TOPIC_JOBS",
        examples=["cts-jobs"],
        description="The Kafka topic to listen to for CDM Task Service job state updates. "
            + "Follows the standard rules for topic names other than periods and underscores "
            + "are not allowed due to ambiguities in how Kafka handles them.",
        min_length=1,
        max_length=249,
        pattern=r"^[a-zA-Z0-9-]+$",
    )]
    kafka_topic_jobs_dlq: Annotated[str, Field(
        validation_alias="CSEP_KAFKA_TOPIC_JOBS_DLQ",
        examples=["cts-jobs-dlq"],
        description="The Kafka topic where CDM Task Service job state update messages should be "
            + "sent if they failed to process, e.g. a Dead Letter Queue. "
            + "Follows the standard rules for topic names other than periods and underscores "
            + "are not allowed due to ambiguities in how Kafka handles them.",
        min_length=1,
        max_length=249,
        pattern=r"^[a-zA-Z0-9-]+$",
    )]
    kafka_group_id: Annotated[str, Field(
        validation_alias="CSEP_KAFKA_GROUP_ID",
        examples=["cdm_event_processor"],
        description="The group ID to use for the Kafka consumer. It is important to read up "
            + "on Kafka consumer groups operation and parallelism if this topic is not well "
            + "understood.",
        min_length=1,
    )]
    kafka_max_poll_interval_ms: Annotated[int, Field(
        validation_alias="CSEP_KAFKA_MAX_POLL_INTERVAL_MS",
        examples=[300 * 1000],
        description="The time interval between polls that will cause the Kafka broker to "
            + "assume the consumer is dead. This value must be longer than the longest expected "
            + "event processing job.",
        gt=0,
    )] = 3600 * 1000
    cdm_task_service_url: Annotated[str, Field(
        validation_alias="CSEP_CDM_TASK_SERVICE_URL",
        examples=["https://ci.kbase.us/servies/cts"],
        description="The root URL of the CDM Task Service.",
        min_length=1,
    )]
    # TODO SECURITY Could make another CTS admin level that only allows reading jobs
    #               See https://kbase-jira.atlassian.net/browse/CDM-124
    cdm_task_service_admin_token: Annotated[str, Field(
        validation_alias="CSEP_CDM_TASK_SERVICE_ADMIN_TOKEN",
        description="A CDM task service token that allows reading all jobs.",
        min_length=1,
    )]
    minio_url: Annotated[str, Field(
        validation_alias="CSEP_MINIO_URL",
        examples=["https://minio.kbase.us"],
        description="The root URL of the Minio instance for storing data.",
        min_length=1,
    )]
    minio_access_key: Annotated[str, Field(
        validation_alias="CSEP_MINIO_ACCESS_KEY",
        examples=["my_minio_user"],
        description="The Minio access key.",
        min_length=1,
    )]
    minio_secret_key: Annotated[str, Field(
        validation_alias="CSEP_MINIO_SECRET_KEY",
        examples=["supersekrit"],
        description="The Minio secret key.",
        min_length=1,
    )]
    minio_secure: Annotated[bool, Field(
        validation_alias="CSEP_MINIO_SECURE",
        description="Whether MinIO/S3 should be accessed over HTTPS when the endpoint "
            + "does not already include a scheme.",
    )] = False
    startup_iceberg_self_test: Annotated[bool, Field(
        validation_alias=AliasChoices(
            "CSEP_STARTUP_ICEBERG_SELF_TEST",
            "CSEP_STARTUP_DELTALAKE_SELF_TEST",
        ),
        description="Whether to run a self test on startup that checks Iceberg "
            + "read / write ability. The test takes seconds to minutes to perform.",
    )] = False
    polaris_catalog_uri: Annotated[str, Field(
        validation_alias=AliasChoices("CSEP_POLARIS_CATALOG_URI", "POLARIS_CATALOG_URI"),
        examples=["https://polaris.kbase.us/api/catalog"],
        description="The Apache Polaris REST catalog URI.",
        min_length=1,
    )]
    polaris_credential: Annotated[str, Field(
        validation_alias=AliasChoices("CSEP_POLARIS_CREDENTIAL", "POLARIS_CREDENTIAL"),
        examples=["client_id:client_secret"],
        description="The Polaris OAuth client credential to use for Iceberg catalog access.",
        min_length=1,
    )]
    polaris_personal_catalog_template: Annotated[str, Field(
        validation_alias="CSEP_POLARIS_PERSONAL_CATALOG_TEMPLATE",
        examples=["user_{user}"],
        description="Template for deriving a user's personal Polaris catalog name from "
            + "the CTS job username. The template must contain a {user} placeholder.",
        min_length=1,
    )] = "user_{user}"
    spark_master_url: Annotated[str, Field(
        validation_alias="CSEP_SPARK_MASTER_URL",
        examples=["https://spark.kbase.us"],
        description="The root URL of the Spark cluster master.",
        min_length=1,
    )]
    spark_driver_host: Annotated[str, Field(
        validation_alias="CSEP_SPARK_DRIVER_HOST",
        examples=["event-processor-1.kbase.us"],
        description="The drive host, e.g. the host on which the event processor is running.",
        min_length=1,
    )]
    spark_jars_dir: Annotated[str, Field(
        validation_alias="CSEP_SPARK_JARS_DIR",
        examples=["/opt/bitnami/spark/jars"],
        description="The path to the Spark jars directory. This environment variable is "
            + "typically provided by the Docker container in which the event processor is "
            + "running.",
        min_length=1,
    )]

    _SAFE_FIELDS = {
        "kafka_bootstrap_servers",
        "kafka_topic_jobs",
        "kafka_topic_jobs_dlq",
        "kafka_group_id",
        "kafka_max_poll_interval_ms",
        "cdm_task_service_url",
        "minio_url",
        "minio_access_key",
        "minio_secure",
        "startup_iceberg_self_test",
        "polaris_catalog_uri",
        "polaris_personal_catalog_template",
        "spark_master_url",
        "spark_driver_host",
        "spark_jars_dir",
    }

    def safe_dump(self) -> dict[str, Any]:
        """
        Return the settings as a dictionary with any sensitive fields (passwords, etc.) redacted.
        """
        return {
            k: v if k in self._SAFE_FIELDS else "REDACTED BY THE MINISTRY OF TRUTH"
            for k, v in self.model_dump().items()
        }
