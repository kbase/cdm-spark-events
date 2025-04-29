# CDM Spark Events Design


TODO
* open ai discussions
* spark streaming docs
   * checkpointing
   * confirm scaling
* error handling, dead letter queue
* Clean up, make coherent

## Nomenclature

* CTS - the [CDM Task Service](https://github.com/kbase/cdm-task-service)

## Document purpose

The CDM Spark events repo is responsible for automatically taking action based on upstream events.
The initial target is processing output from the CTS, but additional event sources
could be added in the future, e.g. responding to data uploaded to a dataplane bucket.

The action taken depends on the nature of the event. For instance, if a CTS job completes and
places job output in the data plane, the event system may run code to import data into CDM
Deltalake tables.

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
  job output in the batch. `forEachBatch` doesn't allow for true parallelism -
  instead it effectively picks the largest job out of the N batch jobs, and sequentially
  runs those large jobs. Given the nature of bioinformatics processing, job output processing
  times are expected to be highly variable, with times ranging from seconds to hours or even days.
* Parallelizing `foreEachBatch` independently would case massive message duplication as each
  SSS instance manages its own Kafka offsets.
  
As such, we will implement with a standard Kafka client like `python-kafka`.

## Design

For now the design will be focused solely on responding to CTS completed job events.

* Spark streaming from Kafka
    * Automatically parallelizes based on `max(kafka_partitions, cluster_cores)`
* `forEach` sink
* Will not support state management (e.g. deduplication, aggregations)
    * Since `forEach` sinks don't guarantee exactly-once operation, deduplication
      isn't particularly useful
* Starts a streaming spark session
    * Adds zip or zips (see Adding importer code below) for importers and dependencies
    * For each Kafka message
    * pulls the CTS job based on the ID
        * Maps the job image name to the python code to run
                * Only python supported
            * Image name -> code only, no tag / digest
            * Code is responsible for dealing with potential processing changes per
              image digest
                * Tag is not supplied as it is mutable, code should key off the digest
        * Create a YAML file with
            * The image name and digest
            * Input file locations in S3
            * Program arguments
                * Not strictly necessary, but some importers may need to key off
                  arguments
        * Run the python code with the YAML file as input
* Develop a library of helper functions for performing `MERGE` inserts into the Deltalake tables


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
* The code to run will need to follow a specific input API as described in `Design`
* There will need to be some way for the event processor to get access to the code to run
* Could start with a simpler implementation and add more complex options later if required
    * If we don't expect frequent importer updates, a simpler option is probably better
    * If we expect 3rd parties to frequently add / update importer code, dynamic
      update may be needed

**DECISION NEEDED**

### 1. Include the code in the event processor repo
* Simplest implementation
* Maintain a single dependencies file (pipenv / uv / ...)
    * Install and zip the dependencies at build time
    * Provide to spark session creating the Kafka stream
* Easy to run integration tests on the importer code
* More complexity for importer authors to deal with
* More PRs for the event processor repo owner to review
* Requires a redeploy of the event image to update importers

### 2. Add an external repo with implementation code at build time
* Isolates the event processor from the importer code
* Maintain a single dependencies file (pipenv / uv / ...)
    * Install and zip the dependencies at build time
    * Provide to spark session creating the Kafka stream
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
    * Provide all dependency zips to the spark session creating the Kafka stream
* Difficult to run integration tests on the importer code
    * May be possible by cloning the event repo in GHA and building the event processor
      image
* Importer authors own PR reviews
* Requires a redeploy of the event image to update importers
* Increases risk of malicious code injection over option 2

### 4. Dynamically update importers from external repo(s)
* As option 2 or 3, but updates repo dynamically without requiring an image rebuild
* May need a location to dynamically pull configuration in order to add new importer repos without
  redeployment
* Increases risk of malicious code injection over option 3
* Not sure how to implement this, would need research. Appears as though the spark session
  would need to be stopped and recreated with new zip files of dependencies. Need to figure out
  how to break out of the event loop, clone the repos, rebuild the dependencies, and restart the
  loop.

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
  the same event may be processed multiple times. Both the CTS and Spark Streaming with a
  `forEach` data sink only guarantee at-least-once event processing.
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
