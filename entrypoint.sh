#!/bin/sh

# TODO SPARK set up the spark environment. Not sure if everything in /opt/scripts/setup.sh
# needs to run, but at minimum the hive setup is necessary


# Function to trim whitespace
trim() {
  echo "$1" | awk '{$1=$1;print}'
}

# 1. Check if token env var is set and non-empty after trimming
if [ -n "$(trim "$CSEP_CDM_TASK_SERVICE_ADMIN_TOKEN")" ]; then
  echo "Using provided CSEP_CDM_TASK_SERVICE_ADMIN_TOKEN environment variable."
else
  # 2. Check if token file path is set
  if [ -z "$CSEP_CDM_TASK_SERVICE_ADMIN_TOKEN_FILE" ]; then
    echo "Error: CSEP_CDM_TASK_SERVICE_ADMIN_TOKEN is not set, and CSEP_CDM_TASK_SERVICE_ADMIN_TOKEN_FILE is not provided." >&2
    exit 1
  fi

  # 3. Check for file existence and read token
  if [ ! -f "$CSEP_CDM_TASK_SERVICE_ADMIN_TOKEN_FILE" ]; then
    echo "Error: Token file '$CSEP_CDM_TASK_SERVICE_ADMIN_TOKEN_FILE' does not exist." >&2
    exit 1
  fi

  token="$(trim "$(cat "$CSEP_CDM_TASK_SERVICE_ADMIN_TOKEN_FILE")")"

  if [ -z "$token" ]; then
    echo "Error: Token file '$CSEP_CDM_TASK_SERVICE_ADMIN_TOKEN_FILE' is empty or only whitespace." >&2
    exit 1
  fi

  export CSEP_CDM_TASK_SERVICE_ADMIN_TOKEN="$token"
  echo "Loaded token from $CSEP_CDM_TASK_SERVICE_ADMIN_TOKEN_FILE into environment."
fi

# exec is needed to replace the shell script as PID 1 so it can recieve sigterm / sigint etc.
exec python /csep/cdmsparkevents/main.py
