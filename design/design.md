# CDM Spark Events Design

## Nomenclature

* CTS - the [CDM Task Service](https://github.com/kbase/cdm-task-service)

## Purpose

The CDM Spark events repo is responsible for automatically taking action based on upstream events.
The initial target is processing output from the CTS, but additional event sources
could be added in the future, e.g. responding to data uploaded to a dataplane bucket.

The action taken depends on the nature of the event. For instance, if a CTS job completes and
places job output in the data plane, the event system may run code to import data into CDM
Deltalake tables.

For example, the CTS could run checkm2 on a set of input files, and when the job is complete,
the event processor parses the checkm2 output in the data plane and inserts the results into
the deltalake tables.

## Notes on Spark Structured Streaming

Since the initial target of the event processor is importing CTS job data into the Spark
Deltalake tables, an obvious choice of framework for the processor would be
Spark Structured Streaming (SSS). However, after an investigation, it seems SSS is ill-suited
to our needs:

* Since an HTTP request must be made to the CTS to fetch the job data, including the output files,
  the SSS data sink must allow for arbitrary code. This
  [limits the sinks](https://spark.apache.org/docs/latest/structured-streaming-programming-guide.html#output-sinks)
  to the `forEach`   and `forEachBatch` sinks.
* `forEach` code
  [runs on the Spark cluster worker](https://spark.apache.org/docs/latest/api/java/org/apache/spark/sql/ForeachWriter.html#process-T-).
  This means that the only the resources of that worker, not the entire cluster, can be used to
  process the job output data. As such `forEach` is not an acceptable choice.
* `forEachBatch` processes data on the driver, and so the driver code can submit full cluster
  jobs for the CTS jobs in the batch. However,
  [only one batch runs at a time](https://spark.apache.org/docs/latest/structured-streaming-programming-guide.html#triggers)
  which means the processing time for the batch is equal to the processing time of largest
  job output in the batch if the batch is parallelized. `forEachBatch` doesn't allow for
  true parallelism - instead, from a performance perspective, it effectively picks the largest job
  out of the N jobs in the batch, and sequentially runs those large jobs for each batch.
  Given the nature of bioinformatics processing, job output processing times are expected to be
  highly variable, with times ranging from seconds to hours or even days.
* Parallelizing `forEachBatch` independently would cause massive message duplication as each
  SSS instance manages its own Kafka offsets.
  
As such, we will implement with a standard Kafka client like `python-kafka`.

## Design

For now the design will be focused solely on responding to CTS completed job events.

* Parallelism is based on scaling multiple Docker containers, each running a sequential,
  single threaded event loop with access to a Spark session.
    * The parallelism is limited by the number of partitions in the Kafka topic.
* Interaction with Kafka will be via the `python-kafka` client.
* For the first iteration, the spark session will be recreated for each job.
    * Future work could investigate whether there are performance improvements from
      sharing the session and whether sharing may cause conflicts between importers.
* For each Kafka message
    * pull the CTS job based on the ID
    * Map the job image name to the python importer code to run
        * Mappings must be made available to the processor (see below)
        * Image name -> code only, no tag or digest
        * The importer code is responsible for dealing with processing changes based
          on the image digest
            * The image tag is not supplied as it is mutable - code should key off the
              digest
    * Create the Spark session
        * Add a zip of dependency python code
        * Only python supported
    * Create a YAML file with
        * The image name and digest
        * Input file locations in S3
        * Program arguments
            * Not strictly necessary, but some importers may need to key off
              arguments
     * Run the python code via the Spark session with the YAML file as input
* Develop a library of helper functions for performing `MERGE` inserts into the Deltalake tables
    * Will be used in most importers
    * Perhaps one already exists

### Error handling

* After a specified number of failures for processing a job's output, the Kafka message, with
  new fields including the error message and stacktrace, will be sent to a Kafka dead letter
  queue (DLQ).
* For now manual processing will be required to examine the messages and start an event processor
  pointed at the DLQ.
* A Kafka DLQ, as opposed to a database entry, makes it easy to reprocess failed events.
* In the future we may want to add the ability for the event processor to automatically shut
  down if it adds too many events to the DLQ in a row, or detects consistent connection failures
  to the Spark cluster or S3.

## Testing

In order to test the event processor, the following services are needed:

### 3rd party
* Mongo
* Minio
* Kafka
* A Spark cluster
* Postgres (for Hive)

### KBase
* Auth2
    * To avoid checking admin tokens into GHA
* CTS
    * Modify to allow setting up without NERSC/JAWS support
        * No need for creds, much faster startup
    * Insert job documents directly into mongo
    * Insert events directly into Kafka
* The event processing image

We will test based on a docker compose file as given the large number and variety of services
required the installation requirements are too high to run via local installs.

## Adding importer code

* The event processor will need to run import code based on the job's Docker image. It will
  need a mapping from job image -> code to run.
* The code to run will need to follow a specific input API as described in `Design`.
* There will need to be some way for the event processor to get access to the code to run.
* We could start with a simpler implementation and add more complex options later if required
    * If we don't expect frequent importer updates, a simpler option is probably better
    * If we expect 3rd parties to frequently add / update importer code, dynamic
      update may be needed

### 1. Include the code in the event processor repo
* Simplest implementation
* Maintain a single dependencies file (pipenv / uv / ...)
    * Install and zip the dependencies at build time
    * Provide to spark session for each job
* Easy to run integration tests on the importer code
* More complexity for importer authors to deal with
* More PRs for the event processor repo owner to review
* Requires a redeploy of the event image to update importers

### 2. Add an external repo with implementation code at build time
* Isolates the event processor from the importer code
* Maintain a single dependencies file (pipenv / uv / ...)
    * Install and zip the dependencies at build time
    * Provide to spark session for each job
    * This requirement has been removed - see Amended Decision below
* Difficult to run integration tests on the importer code
    * May be possible by cloning the event repo in GHA and building the event processor
      image
* All importers in a single repo
* Importer authors own PR reviews
* Requires a redeploy of the event image to update importers
* Increases risk of malicious code injection over option 1

### 3. Add external repos per importer with implementation code at build time
* Isolates the event processor from the importer code
* Isolates various importers from each other
* Multiple dependency files (pipenv / uv / ...)
    * Install and zip each module's dependencies separately at build time
    * Provide the correct dependency zip for each job
* Difficult to run integration tests on the importer code
    * May be possible by cloning the event repo in GHA and building the event processor
      image
* Importer authors own PR reviews
* Requires a redeploy of the event image to update importers
* Increases risk of malicious code injection over option 2

### 4. Dynamically update importers from external repo(s)
* As option 2 or 3, but updates repo dynamically without requiring an image rebuild
    * Check would occur as part of event loop
* May need a location to dynamically pull configuration in order to add new importer repos without
  redeployment
    * Perhaps a configuration file in S3
* Increases risk of malicious code injection over option 3

### Decision

Option 2 was chosen in the the CDM stand up meeting, 2025/05/08.

The rationale is that we can provide a docker compose test file that's much simpler, with
many fewer services, in the independent repo. This should make things easier for importer writers
to understand the system they have to deal with and test their code.

In the future we could investigate options 3 or 4 if the additional complexity seems necessary.

#### Amended Decision

In the CDM standup meeting on 2025/05/13 we decided not to support distributing python dependencies
to the workers:

* The import code is expected to be simple - loading the data into a spark dataframe, performing
  dataframe manipulations, etc. - nothing that would require unusual dependencies.
* Any common libraries that are commonly used can be installed on the workers directly
    * Requires worker restart to deploy new libraries.
* Any unusual processing should happen in the Docker image / container run by the CTS.

## Implications for the CTS

* We may need to have a set of topics for jobs to separate jobs that are expected to 
  require extremely large processing times from more reasonable jobs, as those jobs will
  block the rest of the topic partition from processing.
  * Alternatively long jobs could be detected by the event processor and written to a different
    topic.
* In some cases multiple jobs may need to finish before the event processor can import the data,
  if the data is related in such a way that importing one job's data doesn't make sense.
  The CTS may need something like job sets to which the event processor can respond.
* In some cases a string of jobs may need to complete. Potentially the event manager could
  kick off another job based on the completed job.
* This is reinventing the workflow manager wheel...

## Requirements for importer authors

* Importer authors making use of the CDM events processor must implement importers expecting that
  the same event may be processed multiple times. The CTS only guarantees at-least-once
  event processing.
    * The [MERGE](https://docs.databricks.com/gcp/en/delta/merge) SQL statement
      is one way to ensure duplicate data is not entered into the CDM.
* Importer authors must ensure their code covers different versions of registered CTS images.
  The code should key off the image digest if processing differences are required between different
  image versions.

## Out of scope

* Monitoring the event processor
    * At some point we will want to get alerts if the event processor goes down
* Supporting multiple python versions
    * Only support 3.11 (or .12?) for now

## Approval

This design document was approved in the CDM Tech standup meeting, 2025/05/08.
