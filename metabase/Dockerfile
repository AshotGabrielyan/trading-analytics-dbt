# Metabase + DuckDB driver on a glibc (Debian/Ubuntu) base.
# Based on https://github.com/motherduckdb/metabase_duckdb_driver/blob/main/Dockerfile,
# with versions pinned. The official Metabase image is Alpine (musl) and can't load DuckDB.
FROM eclipse-temurin:21-jre-jammy

ARG METABASE_VERSION=0.63.17
ARG DUCKDB_DRIVER_VERSION=1.5.5.0

ENV MB_PLUGINS_DIR=/home/metabase/plugins/

RUN groupadd -r metabase && useradd -r -g metabase metabase \
    && mkdir -p /home/metabase/plugins \
    && chown -R metabase:metabase /home/metabase

WORKDIR /home/metabase

ADD --chown=metabase:metabase --chmod=755 \
    https://downloads.metabase.com/v${METABASE_VERSION}/metabase.jar /home/metabase/metabase.jar
ADD --chown=metabase:metabase --chmod=755 \
    https://github.com/motherduckdb/metabase_duckdb_driver/releases/download/${DUCKDB_DRIVER_VERSION}/duckdb.metabase-driver.jar \
    /home/metabase/plugins/duckdb.metabase-driver.jar

EXPOSE 3000
USER metabase
CMD ["java", "-jar", "/home/metabase/metabase.jar"]
