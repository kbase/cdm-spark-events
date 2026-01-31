FROM ubuntu:24.04 AS build

RUN apt update && apt install -y git

ENV IMPORTER_COMMIT=dd4cac4d89b6025ec5589554f4cef7fab464ccb7
RUN cd /opt && \
    git clone https://github.com/kbase/cdm-spark-events-importers.git && \
    cd cdm-spark-events-importers && \
    git checkout $IMPORTER_COMMIT && \
    echo $IMPORTER_COMMIT > ./git_commit

WORKDIR /git
COPY .git /git
RUN git rev-parse HEAD > /git/git_commit

FROM ghcr.io/kbase/cdm-spark-standalone:pr-36

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
COPY --from=build /git/git_commit /csep/git_commit
COPY --from=build /opt/cdm-spark-events-importers/cdmeventimporters /importers/cdmeventimporters
COPY --from=build /opt/cdm-spark-events-importers/git_commit /importers/git_commit

ENV PYTHONPATH=/csep:/importers

RUN python /csep/cdmsparkevents/generate_importer_mappings.py \
    /importers \
    /csep/importer_mappings.json

USER spark_user

ENV CSEP_SPARK_JARS_DIR=/opt/bitnami/spark/jars

ENTRYPOINT ["tini", "--", "/csep/entrypoint.sh", "/csep/importer_mappings.json"]
