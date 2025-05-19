FROM ghcr.io/kbase/cdm-spark-standalone:pr-29

USER root

RUN mkdir /uvinstall

WORKDIR /uvinstall

RUN pip install --upgrade pip && \
    pip install uv

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

ENTRYPOINT ["/csep/entrypoint.sh"]
