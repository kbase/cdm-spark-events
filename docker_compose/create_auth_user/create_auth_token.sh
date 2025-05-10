#!/bin/sh

AUTH=$AUTH_URL/testmode/api/V2/testmodeonly

# create user
INJ=$(jq -n --arg name "$USER_NAME" '{"user":$name,"display":"Display_name_here"}')
curl -X POST --json "$INJ" $AUTH/user

# create roles to allow admin useage of service
# TODO CODE make a loop. meh
INJ=$(jq -n --arg role "$HAS_NERSC_ACCOUNT_ROLE" '{"id":$role,"desc":"foo"}')
curl -X POST --json "$INJ" $AUTH/customroles

INJ=$(jq -n --arg role "$KBASE_STAFF_ROLE" '{"id":$role,"desc":"bar"}')
curl -X POST --json "$INJ" $AUTH/customroles

INJ=$(jq -n --arg role "$KBASE_AUTH2_ADMIN_ROLE" '{"id":$role,"desc":"baz"}')
curl -X POST --json "$INJ" $AUTH/customroles

# add all the roles to the user
INJ=$(jq -n \
    --arg name "$USER_NAME" \
    --arg role1 "$HAS_NERSC_ACCOUNT_ROLE" \
    --arg role2 "$KBASE_STAFF_ROLE" \
    --arg role3 "$KBASE_AUTH2_ADMIN_ROLE" \
    '{"user":$name,"customroles":[$role1,$role2,$role3]}'
)
curl -X PUT --json "$INJ" $AUTH/userroles

# Create a token
INJ=$(jq -n --arg name "$USER_NAME" '{"user":$name,"type":"Dev"}')
JSON=$(curl -s -X POST --json "$INJ" $AUTH/token)

# pull the token out of the JSON and save it
echo $JSON | jq -r .token > $TOKEN_OUTFILE

# This seems to force an output flush, otherwise the curl output doesn't necessarily end up
# in the docker logs, which makes debugging a pain'
echo "\nToken written to $TOKEN_OUTFILE"
