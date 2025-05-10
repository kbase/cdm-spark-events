FROM ubuntu:24.04

RUN apt update && apt install -y curl jq

COPY create_auth_token.sh /create_auth_token.sh

ENTRYPOINT ["/create_auth_token.sh"]
