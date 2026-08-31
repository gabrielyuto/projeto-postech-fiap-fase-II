# Kubernetes (Kustomize: base + overlays)

Esta pasta usa [Kustomize](https://kubectl.docs.kubernetes.io/guides/introduction/kustomize/)
para evitar reescrever manifests inteiros a cada ambiente.

```
k8s/
  base/                     # Deployments/Services/ConfigMaps comuns a TODOS os ambientes
    auth-service/
    flag-service/
    targeting-service/
    evaluation-service/
    analytics-service/
    postgres-init/          # Schema SQL (auth_db, flags_db, targeting_db) - reaproveitado por dev e produção
  overlays/
    development/            # Minikube: infra local (Postgres/Redis/ElasticMQ/DynamoDB local) + segredos fake
    production/             # EKS: recursos externos da AWS (RDS/ElastiCache/SQS/DynamoDB reais) + imagens do ECR
```

Nenhum arquivo em `base/` tem `namespace` ou segredo fixado — cada overlay decide o
namespace, as credenciais e, no caso de produção, os endpoints da AWS.

## Ambiente de desenvolvimento (Minikube)

Compare com o fluxo antigo baseado em `kubectl apply -f k8s/development/<serviço>`:
agora um único comando aplica tudo.

```bash
# 1. Construir as imagens dentro do Minikube (imagePullPolicy: Never)
minikube image build -t projeto-postech-fiap-fase-ii-auth-service:latest ./docker/services/auth-service-main
minikube image build -t projeto-postech-fiap-fase-ii-flag-service:latest ./docker/services/flag-service-main
minikube image build -t projeto-postech-fiap-fase-ii-targeting-service:latest ./docker/services/targeting-service-main
minikube image build -t projeto-postech-fiap-fase-ii-evaluation-service:latest ./docker/services/evaluation-service-main
minikube image build -t projeto-postech-fiap-fase-ii-analytics-service:latest ./docker/services/analytics-service-main

# 2. Aplicar todo o overlay de uma vez
kubectl apply -k k8s/overlays/development

# 3. Acompanhar
kubectl get pods -n development
```

Para inspecionar o YAML final sem aplicar: `kubectl kustomize k8s/overlays/development`.

Os segredos de `overlays/development/secrets/*.yaml` são credenciais fake, iguais às que já
existiam no repositório (`postgres/postgres`, `redis123`, `admin-secreto-123`, chaves AWS
`fake`) — servem só para o cluster local e continuam versionadas normalmente.

## Ambiente de produção (EKS)

Em produção, Postgres, Redis, SQS e DynamoDB **não rodam como pods**: são recursos
gerenciados da AWS (RDS, ElastiCache, SQS e DynamoDB reais). O overlay `production` não
inclui os StatefulSets/Deployments de infraestrutura local — apenas os 5 serviços da
aplicação, apontando para esses recursos externos via ConfigMap/Secret.

### Recursos AWS provisionados (conta 180981210379, região us-east-1)

- RDS PostgreSQL: `arn:aws:rds:us-east-1:180981210379:db:togglemaster-db`
  (`togglemaster-db.cx3w8waoqxrk.us-east-1.rds.amazonaws.com:5432`, usuário `postgres`,
  senha gerenciada pelo Secrets Manager).
- ElastiCache Redis: `arn:aws:elasticache:us-east-1:180981210379:replicationgroup:evaluation-cache`
  (`clustercfg.evaluation-cache.9xskzb.use1.cache.amazonaws.com:6379`, TLS obrigatório,
  sem AUTH token).
- Fila SQS: `arn:aws:sqs:us-east-1:180981210379:analytics-queue`.
- Tabela DynamoDB: `arn:aws:dynamodb:us-east-1:180981210379:table/analytics-db`
  (partition key `event_id`, tipo String).
- Repositórios no ECR: `togglemaster/auth-service`, `togglemaster/flag-service`,
  `togglemaster/targeting-service`, `togglemaster/evaluation-service`,
  `togglemaster/analytics-service`.

Este lab não provisiona as IAM Roles esperadas para IRSA, então `evaluation-service` e
`analytics-service` autenticam na AWS via `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/
`AWS_SESSION_TOKEN` definidos diretamente nos respectivos `Secret`s (veja a seção de
segredos abaixo) — o SDK usa essas variáveis de ambiente antes de tentar qualquer role.
Nenhum serviço usa ServiceAccount própria.

### Build e push das imagens (ECR)

```bash
AWS_ACCOUNT_ID=<sua-conta>
AWS_REGION=us-east-1
TAG=$(git rev-parse --short HEAD)   # prefira uma tag imutável a "latest"

aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

for svc in auth-service flag-service targeting-service evaluation-service analytics-service; do
  docker build -t "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/togglemaster/$svc:$TAG" "./services/${svc}-main"
  docker push "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/togglemaster/$svc:$TAG"
done
```

Depois, atualize as referências de imagem do overlay (isso deve rodar na pipeline de
CI/CD, não manualmente):

```bash
cd k8s/overlays/production
for svc in auth-service flag-service targeting-service evaluation-service analytics-service; do
  kustomize edit set image "$svc=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/togglemaster/$svc:$TAG"
done
```

### Segredos de produção

Os manifests em `overlays/production/secrets/*.yaml` são `Secret`s literais com o campo
`data` já em base64, apontando para os recursos reais acima (RDS, ElastiCache, SQS,
DynamoDB). Como isso versiona segredos reais no git (aceitável neste laboratório, com
credenciais temporárias do AWS Academy), **não replique esse padrão em uma conta AWS
de produção real** — prefira um cofre de segredos (Secrets Manager + External Secrets
Operator, SOPS, etc.).

`SERVICE_API_KEY` em `evaluation-service-secret.yaml` é um placeholder
(`REPLACE_AFTER_DEPLOY`): depois que o `auth-service` estiver no ar, gere uma chave real e
aplique-a:

```bash
kubectl exec -n production deploy/auth-service -- \
  wget -qO- --post-data '{"name":"evaluation-service"}' \
  --header 'Content-Type: application/json' \
  --header "Authorization: Bearer $(kubectl get secret auth-service-secret -n production -o jsonpath='{.data.MASTER_KEY}' | base64 -d)" \
  http://localhost:8001/admin/keys

kubectl patch secret evaluation-service-secret -n production --type merge \
  -p '{"data":{"SERVICE_API_KEY":"<novo-valor-em-base64>"}}'
kubectl rollout restart deployment/evaluation-service -n production
```

`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_SESSION_TOKEN` são definidos nos secrets
de `evaluation-service` e `analytics-service` (credenciais temporárias da sessão AWS
Academy). O SDK usa essas variáveis de ambiente antes de tentar IRSA/instance role — em
uma conta de produção real, prefira recriar o IRSA (ServiceAccount + IAM Role) em vez
deste workaround.

### Schema do PostgreSQL (RDS)

O schema (`auth_db`, `flags_db`, `targeting_db`) é o mesmo em qualquer ambiente e vive em
[base/postgres-init](base/postgres-init/configmap.yaml). Como o RDS não roda
`docker-entrypoint-initdb.d`, um Job aplica o mesmo SQL uma única vez:

```bash
kubectl apply -k k8s/overlays/production
kubectl logs -n production job/postgres-schema-init -f
```

Se precisar rodar de novo (ex: para recriar uma tabela), apague o Job antes:
`kubectl delete job -n production postgres-schema-init`.

### Aplicar

```bash
kubectl apply -k k8s/overlays/production
kubectl get pods -n production
kubectl rollout status deployment/evaluation-service -n production
```

## Migração do `k8s/development` antigo

A estrutura plana anterior (`k8s/development/<serviço>/*.yml`, aplicada com múltiplos
`kubectl apply -f`) foi removida: `k8s/overlays/development` já foi validado ponta a ponta
(health checks, fluxo de avaliação, cache Redis e pipeline SQS → analytics → DynamoDB) e é
o substituto direto.
