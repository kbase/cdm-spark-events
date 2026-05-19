#!/bin/bash

echo -n "Event processor git commit: " && cat /csep/git_commit
echo -n "Importer repo  git commit : " && cat /importers/git_commit

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

if [ -n "$(trim "$CSEP_POLARIS_CREDENTIAL")" ]; then
  echo "Using provided CSEP_POLARIS_CREDENTIAL environment variable."
else
  if [ -z "$CSEP_POLARIS_CREDENTIAL_FILE" ]; then
    echo "Error: CSEP_POLARIS_CREDENTIAL is not set, and CSEP_POLARIS_CREDENTIAL_FILE is not provided." >&2
    exit 1
  fi

  if [ ! -f "$CSEP_POLARIS_CREDENTIAL_FILE" ]; then
    echo "Error: Polaris credential file '$CSEP_POLARIS_CREDENTIAL_FILE' does not exist." >&2
    exit 1
  fi

  polaris_credential="$(trim "$(cat "$CSEP_POLARIS_CREDENTIAL_FILE")")"

  if [ -z "$polaris_credential" ]; then
    echo "Error: Polaris credential file '$CSEP_POLARIS_CREDENTIAL_FILE' is empty or only whitespace." >&2
    exit 1
  fi

  export CSEP_POLARIS_CREDENTIAL="$polaris_credential"
  echo "Loaded Polaris credential from $CSEP_POLARIS_CREDENTIAL_FILE into environment."
fi

python /csep/cdmsparkevents/main.py "$@"
