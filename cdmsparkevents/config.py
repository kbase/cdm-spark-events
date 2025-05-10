"""
Configuration for the event handler.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Annotated, Any


class Config(BaseSettings):
    """
    The configuration for the CDM events processor.
    """
    model_config = SettingsConfigDict(case_sensitive=True, str_strip_whitespace=True)
    
    kafka_bootstrap_servers: Annotated[str, Field(
        validation_alias="CSEP_KAFKA_BOOTSTRAP_SERVERS",
        example="localhost:9092",
        description="The comma separated bootstrap servers list for Kafka.",
        min_length=1,
    )]
    kafka_topic_jobs: Annotated[str,  Field(
        validation_alias="CSEP_KAFKA_TOPIC_JOBS",
        example="cts-jobs",
        description="The Kafka topic to listen to for CDM Task Service job state updates. "
            + "Follows the standard rules for topic names other than periods and underscores "
            + "are not allowed due to ambiguities in how Kafka handles them.",
        min_length=1,
        max_length=249,
        pattern=r"^[a-zA-Z0-9-]+$",
    )]
    kafka_topic_jobs_dlq: Annotated[str, Field(
        validation_alias="CSEP_KAFKA_TOPIC_JOBS_DLQ",
        example="cts-jobs-dlq",
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
        example="cdm_event_processor",
        description="The group ID to use for the Kafka consumer. It is important to read up "
            + "on Kafka consumer groups operation and parallelism if this topic is not well "
            + "understood.",
        min_length=1,
    )]
    kafka_max_poll_interval_ms: Annotated[int, Field(
        validation_alias="CSEP_KAFKA_MAX_POLL_INTERVAL_MS",
        example=300 * 1000,
        description="The time interval between polls that will cause the Kafka broker to "
            + "assume the consumer is dead. This value must be longer than the longest expected "
            + "event processing job.",
        gt=0,
    )] = 3600 * 1000
    cdm_task_service_url: Annotated[str, Field(
        validation_alias="CSEP_CDM_TASK_SERVICE_URL",
        example="https://ci.kbase.us/servies/cts",
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
    
    _SAFE_FIELDS = {
        "kafka_bootstrap_servers", 
        "kafka_topic_jobs",
        "kafka_topic_jobs_dlq",
        "kafka_group_id",
        "kafka_max_poll_interval_ms",
        "cdm_task_service_url",
    }
    
    def safe_dump(self) -> dict[str, Any]:
        """
        Return the settings as a dictionary with any sensitive fields (passwords, etc.) redacted.
        """
        return {
            k: v if k in self._SAFE_FIELDS else "REDACTED BY THE MINISTRY OF TRUTH"
            for k, v in self.model_dump().items()
        }
