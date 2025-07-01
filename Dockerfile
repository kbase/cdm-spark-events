FROM ubuntu:24.04 AS build

ENV IMPORTER_COMMIT=ccf404822cf45efef3def523342389de712548fc

RUN apt update && apt install -y git

RUN cd /opt && \
    git clone https://github.com/kbase/cdm-spark-events-importers.git && \
    cd cdm-spark-events-importers && \
    git checkout $IMPORTER_COMMIT && \
    echo $IMPORTER_COMMIT > ./git_commit

FROM ghcr.io/kbase/cdm-spark-standalone:pr-42

USER root

RUN mkdir /uvinstall

WORKDIR /uvinstall

COPY pyproject.toml uv.lock .python-version .

ENV UV_PROJECT_ENVIRONMENT=/opt/bitnami/python
RUN uv sync --locked --inexact --no-dev

RUN mkdir /csep && mkdir /importers

WORKDIR /csep

COPY entrypoint.sh /csep/
COPY cdmsparkevents /csep/cdmsparkevents
COPY --from=build /opt/cdm-spark-events-importers/cdmeventimporters /importers/cdmeventimporters
COPY --from=build /opt/cdm-spark-events-importers/git_commit /importers/git_commit

ENV PYTHONPATH=/csep:/importers

RUN python /csep/cdmsparkevents/generate_importer_mappings.py \
    /importers \
    /csep/importer_mappings.json

USER spark_user

ENV CSEP_SPARK_JARS_DIR=/opt/bitnami/spark/jars

ENTRYPOINT ["tini", "--", "/csep/entrypoint.sh", "/csep/importer_mappings.json"]
