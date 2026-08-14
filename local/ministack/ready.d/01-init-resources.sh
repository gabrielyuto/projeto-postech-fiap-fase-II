#!/bin/bash
set -e

ENDPOINT="http://localhost:4566"

echo "Criando fila SQS..."
aws --endpoint-url=$ENDPOINT sqs create-queue --queue-name evaluation-queue

echo "Criando tabela DynamoDB..."
aws --endpoint-url=$ENDPOINT dynamodb create-table \
  --table-name ToggleMasterAnalytics \
  --attribute-definitions AttributeName=event_id,AttributeType=S \
  --key-schema AttributeName=event_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST

echo "Recursos criados com sucesso!"