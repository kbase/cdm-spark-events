FROM --platform=linux/amd64 ghcr.io/kbase/cdm-spark-standalone:pr-28

USER root

RUN mkdir /uvinstall

WORKDIR /uvinstall

RUN pip install --upgrade pip && \
    pip install uv

COPY pyproject.toml uv.lock .python-version .

ENV UV_PROJECT_ENVIRONMENT=/opt/bitnami/python
RUN uv sync --locked --inexact --no-dev

COPY cdmsparkevents /cdmsparkevents

ENV PYTHONPATH=/

USER spark_user

ENTRYPOINT ["python", "/cdmsparkevents/main.py"]
