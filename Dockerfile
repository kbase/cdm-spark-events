FROM ghcr.io/kbase/cdm-spark-standalone:pr-34

USER root

RUN mkdir /uvinstall

WORKDIR /uvinstall

COPY pyproject.toml uv.lock .python-version .

ENV UV_PROJECT_ENVIRONMENT=/opt/bitnami/python
RUN uv sync --locked --inexact --no-dev

RUN mkdir /csep

COPY entrypoint.sh /csep/
COPY cdmsparkevents /csep/cdmsparkevents

ENV PYTHONPATH=/csep

WORKDIR /csep

USER spark_user

ENV CSEP_SPARK_JARS_DIR=/opt/bitnami/spark/jars

ENTRYPOINT ["tini", "--", "/csep/entrypoint.sh"]
