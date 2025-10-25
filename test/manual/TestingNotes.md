Testing this is a pain, need to either figure out better tools or add an automated test suite

Assumes docker compose is running.

# Run a startup test

To run the built in startup test, set the `CSEP_STARTUP_DELTALAKE_SELF_TEST` environment
variable to 'true` in the docker compose file and restart the compose.

The startup test writes and reads data to Deltalake tables and thus tests that minio, the spark
master and worker(s), and the event processor can communicate with each other.

# Run an integration test

The integration test tests the flow through the event processor from a kafka message to data
being written in Minio. It uses a built in importer that creates a trivial employee table.
To run the test, send a message to Kafka while the docker compose is up:

```
docker compose exec cdm-events python test/manual/send_kafka_message.py -t '<payload>'
```

`<payload>` is a JSON string. The example below has line breaks for clarity but
whitespace should be removed in general.

```
{
  "special_event_type": "integration_test",
  "input_data": <input data, see below>,
  "app_name_prefix": <the spark app name, optional>,
  "mode": <"update" or anything else, see below>,
}
```

`"input_data"` contains input data to add to the integration test table. It's a list of lists,
where each entry in the outer list is DB row. Each row consists of, in order, an integer
employee ID and string employee name.

If `"mode"` is not provided or `"update"` then matching rows in data based on the
employee ID will be overwritten; otherwise they're ignored. 

After sending the Kafka message, watch the event processor logs to see the results of the test.

Note that the integration test does not access the CTS, nor does it update the Dead Letter Queue
if an error occurs.

# Run a checkm2 test

## Load test files to minio

```
mc cp --recursive --checksum crc64nvme test/manual/data/* local9000/test-events/testfiles/
```

## Add a job to the CTS

Image name comes from the checkm2 importer yaml

```
$ docker compose exec cdm-task-service python /cts_helpers/add_cts_job_to_mongo.py \
    my_job_id complete ghcr.io/kbasetest/cdm_checkm2 sha256:digest_here \
    test-events/testfiles/run1/quality_report.tsv crc1aaaaaaaa \
    test-events/testfiles/run2/quality_report.tsv crc2aaaaaaaa
```

## Create target table in spark (optionally)

If the table doesn't exist, the importer will create it. However, to test proper merging
the table can be created ahead of time. In any case, the spark session will be necessary to
read the results.

```
$ docker compose exec -it --user root cdm-events bash
root@3568743395c1:/csep# pip install ipython
root@3568743395c1:/csep# export CSEP_CDM_TASK_SERVICE_ADMIN_TOKEN=$(cat /shared/token.txt | tr -d '[:space:]')
root@3568743395c1:/csep# ipython

In [1]: from cdmsparkevents.config import Config

In [2]: cfg = Config()

In [3]: from cdmsparkevents.spark import spark_session

In [4]: spark = spark_session(cfg, "some_user", "myapp")
25/05/27 23:33:42 WARN NativeCodeLoader: Unable to load native-hadoop library for your platform... using builtin-java classes where applicable
Setting default log level to "WARN".
To adjust logging level use sc.setLogLevel(newLevel). For SparkR, use setLogLevel(newLevel).
25/05/27 23:33:44 WARN Utils: spark.executor.instances less than spark.dynamicAllocation.minExecutors is invalid, ignoring its setting, please update your configs.

# from the checkm2 importer yaml. May want to make this easier to override
In [5]: table = "u_some_user__autoimport.checkm2"

In [6]: db = table.split(".")[0]

In [11]: spark.sql(f"CREATE DATABASE {db}")
Out[11]: DataFrame[]

In [13]: df = spark.read.option("header", True).option("sep", "\t").csv("s3a://t
       ⋮ est-events/testfiles/checkm2_db_init.tsv")

In [14]: from pyspark.sql.functions import col

In [16]: from pyspark.sql.types import StructType, StructField, StringType, Floa
       ⋮ tType, IntegerType, Row

In [18]: _CHECKM2_DB_SCHEMA = StructType([
    ...:     StructField("Name", StringType()),
    ...:     StructField("cts_job_id", StringType()),
    ...:     StructField("Completeness", FloatType()),
    ...:     StructField("Contamination", FloatType()),
    ...:     StructField("Completeness_Model_Used", StringType()),
    ...:     StructField("Translation_Table_Used", IntegerType()),
    ...:     StructField("Coding_Density", FloatType()),
    ...:     StructField("Contig_N50", IntegerType()),
    ...:     StructField("Average_Gene_Length", FloatType()),
    ...:     StructField("Genome_Size", IntegerType()),
    ...:     StructField("GC_Content", FloatType()),
    ...:     StructField("Total_Coding_Sequences", IntegerType()),
    ...:     StructField("Total_Contigs", IntegerType()),
    ...:     StructField("Max_Contig_Length", IntegerType()),
    ...:     StructField("Additional_Notes", StringType(), True),  # allow nulls
    ...: ])

# Coerce the table into the expected schema
In [19]: columns = [
    ...:     (col(field.name).cast(field.dataType)).alias(field.name)
    ...:     for field in _CHECKM2_DB_SCHEMA
    ...: ]


In [20]: df = df.select(*columns)

In [23]: df.write.mode("overwrite").option("compression", "snappy").format("delt
       ⋮ a").saveAsTable(table)

In [24]: spark.stop()
```

Stopping the spark session is important as otherwise the importer will hang forever waiting
for cores on the spark workers. Adding cores in the docker compose file is another option.
 
## Add an event to kafka

```
docker compose exec cdm-events python test/manual/send_kafka_message.py -t '{"job_id":"my_job_id","state":"complete"}'
```

## Check the results

Watch the cdm-events logs until the import completes or errors out. Then do one of the below.

### Check the table contents

Start a spark session as shown above and check the contents of the table include the information
from the new job:

```
In [7]: df = spark.sql(f"SELECT * FROM {table}")
                                                                                
In [8]: df.show()
+-------------+----------+------------+-------------+-----------------------+----------------------+--------------+----------+-------------------+-----------+----------+----------------------+-------------+-----------------+----------------+
|         Name|cts_job_id|Completeness|Contamination|Completeness_Model_Used|Translation_Table_Used|Coding_Density|Contig_N50|Average_Gene_Length|Genome_Size|GC_Content|Total_Coding_Sequences|Total_Contigs|Max_Contig_Length|Additional_Notes|
+-------------+----------+------------+-------------+-----------------------+----------------------+--------------+----------+-------------------+-----------+----------+----------------------+-------------+-----------------+----------------+
|GCA_bsubtilis| my_job_id|        0.91|         0.27|                    mod|                     9|          0.49|       150|                0.5|         46|      0.93|                    36|            5|               16|            whoo|
|    GCA_ecoli| my_job_id|         0.9|         0.26|                 model4|                     8|          0.48|       149|               0.49|         45|      0.92|                    35|            4|               15|            NULL|
|     GCA_keep|  old_job2|        0.88|         0.24|                 model2|                     6|          0.46|       147|               0.47|         43|       0.9|                    33|            2|               13|          Lovely|
|  GCA_replace| my_job_id|        0.89|         0.25|                 model3|                     7|          0.47|       148|               0.48|         44|      0.91|                    34|            3|               14|           hello|
+-------------+----------+------------+-------------+-----------------------+----------------------+--------------+----------+-------------------+-----------+----------+----------------------+-------------+-----------------+----------------+

```

### Check the DLQ on error

An error can be forced by adding an extra, non-existant file when creating CTS job earlier.

To check the contents of the DLQ:

```
$ docker compose exec cdm-events python test/manual/dump_kafka_dlq.py
{'checksum': None,
 'headers': [],
 'key': None,
 'leader_epoch': 0,
 'offset': 0,
 'partition': 2,
 'serialized_header_size': -1,
 'serialized_key_size': -1,
 'serialized_value_size': 143,
 'timestamp': 1749080650235,
 'timestamp_type': 0,
 'topic': 'cts-jobs-dlq',
 'value': b'{"job_id": "my_job_id", "status": "complete", "error_dlq": "Mess'
          b"age has missing required keys:\\n{'job_id': 'my_job_id', 'status'"
          b': \'complete\'}"}'}
{'checksum': None,
 'headers': [],
 'key': None,
 'leader_epoch': 0,
 'offset': 1,
 'partition': 2,
 'serialized_header_size': -1,
 'serialized_key_size': -1,
 'serialized_value_size': 627,
 'timestamp': 1749080857442,
 'timestamp_type': 0,
 'topic': 'cts-jobs-dlq',
 'value': b'{"job_id": "my_job_id", "state": "complete", "error_dlq": "No ch'
          b'eckm2 quality report files found", "error_dlq_trace": "Traceback'
          b' (most recent call last):\\n  File \\"/csep/cdmsparkevents/eventlo'
          b'op.py\\", line 249, in _process_message\\n    self._run_importer(i'
          b'mage, f\\"job_id_{job_id}\\", job_id, imp_job_info)\\n  File \\"'
          b'/csep/cdmsparkevents/eventloop.py\\", line 314, in _run_importer\\'
          b'n    mod[0].run_import(get_spark, job_info, mod[1])\\n  File \\"/i'
          b'mporters/cdmeventimporters/checkm2.py\\", line 52, in run_import\\'
          b'n    raise ValueError(\\"No checkm2 quality report files found\\")'
          b'\\nValueError: No checkm2 quality report files found\\n"}'}
```
