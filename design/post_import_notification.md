# Post import notifications

## Nomenclature and references

* CSE - CDM Spark events, this repo
* CTS - the CDM Task Service, https://github.com/kbase/cdm-task-service

## Document purpose

Define a design for notifying users when an import coordinated by the CSE import system of the
output of a CTS job is complete.

## Proposed design

* Add administrative metadata key-value pairs to CTS jobs.
    * Only system administrators can set administrative metadata
        * In future work we could add more specific administrator roles into the CTS,
            as opposed to the single full administrator role that currently exists
    * Generally useful for tagging jobs in future use cases
    * In the current design the key value pairs are not queryable but that could
      be explored in the future
    * Adding a key or keys to admin metadata overwrites any extant matching keys
      but extant non-matching keys are unaffected
        * E.g. the metadata is mutable
* When a CSE import for a CTS job begins, completes or fails, the CSE adds a key value pair
  to the CTS job:
    * `cse_event_processing_<started, complete, error>: <iso8601 date>`
* Add an endpoint to the CTS at `/jobs/<job_id>/state` that returns a minimal amount of
  information for the job that allows the user to determine the job's, and post job event
  processor's, state
    * E.g. the job state, the last job update time, the admin metadata as a minimum
    
### Benefits

* The overall state of the data processing is viewable in one place.
    * The user / client can then check for updates to the event processing state for the job in
      the same way they check the state of the job proper.
* The CTS remains decoupled from the downstream CSE; it does not know the CSE exists
    * To the CTS the administrative metadata are opaque key value pairs

## Rejected ideas

* Have the CSE send an event to Kafka and have some other downstream system handle notifying the
  user
    * Much more complex, unclear if there are other downstream processes that need
      this information
    * Means the user needs to query the job status until it's complete and then 
      switch to another service to query
    * Can be added later if needed
* Have the CSE send information to a separate database and add a separate service that allows
  querying the database for event status
    * Adds more infrastructure that already mostly exists in the form of the CTS
    * Separates the overall data flow status into two locations
    * Means the user needs to query the job status until it's complete and then 
      switch to another service to query

## Potential future work

* Explore server side events or similar technologies so the CTS can push updates to the client
  rather than forcing the client to poll
* If a service ever submits CTS jobs, add webhooks for callbacks