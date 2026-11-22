#!/usr/bin/env bash
set -euo pipefail
umask 077
cat > etc/conf/hibernate.properties <<EOF
hibernate.connection.driver_class=org.postgresql.Driver
hibernate.connection.url=jdbc:postgresql://postgres:5432/unitycatalog
hibernate.connection.username=lakehouse
hibernate.connection.password=${POSTGRES_PASSWORD}
hibernate.hbm2ddl.auto=update
hibernate.archive.autodetection=class
hibernate.show_sql=false
EOF
cat > etc/conf/server.properties <<EOF
server.env=dev
server.authorization=disable
server.managed-table.enabled=true
storage-root.tables=s3://${R2_BUCKET}/warehouse
s3.bucketPath.0=s3://${R2_BUCKET}
s3.region.0=auto
# UC's legacy bucket parser requires a non-empty role field even for a custom generator.
# This sentinel is never sent to AWS; R2CredentialGenerator performs local signing.
s3.awsRoleArn.0=arn:aws:iam::000000000000:role/r2-local-signer-unused
s3.credentialGenerator.0=lakehouse.R2CredentialGenerator
EOF
exec bin/start-uc-server
