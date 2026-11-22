#!/usr/bin/env bash
# Starts a throwaway SQL Server for the tests and exports TEST_SQL_URL to the following steps.
# The sa password is generated for this run only and masked in the logs, so no secret is stored anywhere.
set -euo pipefail

password="Ci-$(openssl rand -hex 12)-A1"
echo "::add-mask::${password}"

docker run -d --name sql -e ACCEPT_EULA=Y -e "MSSQL_SA_PASSWORD=${password}" -p 1433:1433 \
  mcr.microsoft.com/mssql/server:2022-latest >/dev/null

for _ in $(seq 1 60); do
  if docker exec sql /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "${password}" -Q "SELECT 1" -b -o /dev/null 2>/dev/null; then
    echo "TEST_SQL_URL=mssql://sa:${password}@localhost:1433/master" >> "${GITHUB_ENV}"
    echo "SQL Server is ready"
    exit 0
  fi
  sleep 2
done

docker logs sql | tail -20
echo "SQL Server did not start in time" >&2
exit 1
