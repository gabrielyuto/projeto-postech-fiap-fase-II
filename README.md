# Projeto POS-TECH FIAP - Fase II

Plataforma de feature flags (ToggleMaster) composta por 5 microsserviços:

| Serviço | Linguagem | Porta | Função |
|---|---|---|---|
| `auth-service` | Go | 8001 | Emite/valida chaves de API |
| `flag-service` | Python | 8002 | CRUD de feature flags |
| `targeting-service` | Python | 8003 | Regras de segmentação |
| `evaluation-service` | Go | 8004 | Avalia flags para um usuário, publica evento no SQS |
| `analytics-service` | Python | 8005 | Consome o SQS e persiste eventos no DynamoDB |

O provisionamento de infraestrutura (Kubernetes) usa [Kustomize](https://kubectl.docs.kubernetes.io/guides/introduction/kustomize/)
com uma base comum em [k8s/base](k8s/base) e dois overlays em [k8s/overlays](k8s/overlays):
`development` (Minikube, com toda a infra local) e `production` (EKS, com recursos reais da AWS).
Detalhes completos de cada overlay estão em [k8s/README.md](k8s/README.md) — este README traz
o passo a passo resumido para provisionar cada ambiente do zero.

## Opção mais simples: Docker Compose (sem Kubernetes)

Para rodar tudo localmente sem Kubernetes, com Postgres, Redis, ElasticMQ e DynamoDB local:

```bash
docker compose up --build
```

Os serviços sobem nas portas listadas na tabela acima. Cada serviço lê variáveis de um
`.env` próprio em `services/<serviço>-main/.env` (veja os `README.md` de cada serviço).

## Provisionando localmente com Kubernetes (overlay `development`)

Pré-requisitos: [Minikube](https://minikube.sigs.k8s.io/) e o addon de ingress habilitado.

```bash
minikube start
minikube addons enable ingress

# 1. Construir as imagens dentro do Minikube (imagePullPolicy: Never)
minikube image build -t projeto-postech-fiap-fase-ii-auth-service:latest ./services/auth-service-main
minikube image build -t projeto-postech-fiap-fase-ii-flag-service:latest ./services/flag-service-main
minikube image build -t projeto-postech-fiap-fase-ii-targeting-service:latest ./services/targeting-service-main
minikube image build -t projeto-postech-fiap-fase-ii-evaluation-service:latest ./services/evaluation-service-main
minikube image build -t projeto-postech-fiap-fase-ii-analytics-service:latest ./services/analytics-service-main

# 2. Aplicar todo o overlay de desenvolvimento de uma vez
kubectl apply -k k8s/overlays/development

# 3. Acompanhar
kubectl get pods -n development
```

O overlay `development` já inclui, como pods no próprio cluster: Postgres, Redis, ElasticMQ
(emulando SQS) e DynamoDB local — além de segredos fake versionados em
[k8s/overlays/development/secrets](k8s/overlays/development/secrets). Nenhuma credencial
real da AWS é necessária neste ambiente.

Para inspecionar o YAML final gerado pelo Kustomize sem aplicar:

```bash
kubectl kustomize k8s/overlays/development
```

Para reaplicar após alterar código de um serviço, reconstrua a imagem (passo 1) e rode:

```bash
kubectl rollout restart deployment/<nome-do-serviço> -n development
```

## Provisionando em produção na AWS (overlay `production`, EKS)

Em produção, Postgres, Redis, SQS e DynamoDB **não rodam como pods**: o overlay aponta para
recursos reais da AWS (RDS, ElastiCache, SQS e DynamoDB) via ConfigMap/Secret. Pré-requisitos:

- Cluster EKS já criado, com `kubectl` configurado no contexto correto.
- RDS PostgreSQL, ElastiCache Redis, fila SQS e tabela DynamoDB já provisionados.
- Repositórios ECR criados para os 5 serviços.
- Credenciais AWS válidas (`aws sts get-caller-identity` funcionando) para build/push de
  imagens e, neste laboratório, para autenticação do `evaluation-service`/`analytics-service`
  (veja a nota sobre IRSA abaixo).

```bash
# 1. Build e push das imagens para o ECR (ver k8s/README.md para o script completo)
AWS_ACCOUNT_ID=<sua-conta>
AWS_REGION=us-east-1
TAG=$(git rev-parse --short HEAD)

aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

for svc in auth-service flag-service targeting-service evaluation-service analytics-service; do
  docker build -t "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/togglemaster/$svc:$TAG" "./services/${svc}-main"
  docker push "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/togglemaster/$svc:$TAG"
done

# 2. Ajustar os endpoints reais da AWS em k8s/overlays/production/secrets/*.yaml
#    (RDS, ElastiCache, SQS, DynamoDB — ver k8s/README.md)

# 3. Aplicar o overlay de produção
kubectl apply -k k8s/overlays/production

# 4. Acompanhar
kubectl get pods -n production
kubectl rollout status deployment/evaluation-service -n production
```

O schema do Postgres (`auth_db`, `flags_db`, `targeting_db`) é aplicado automaticamente pelo
Job `postgres-schema-init` no primeiro `apply` (o RDS não roda `docker-entrypoint-initdb.d`).

> **Nota sobre credenciais AWS (IRSA):** o padrão correto de produção é usar IRSA
> (ServiceAccount + IAM Role via OIDC do EKS) para o `evaluation-service` e o
> `analytics-service` autenticarem no SQS/DynamoDB. Neste laboratório (AWS Academy) não é
> possível criar as IAM Roles necessárias, então as credenciais são fornecidas via
> `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_SESSION_TOKEN` diretamente nos secrets
> desses dois serviços (o SDK da AWS prioriza variáveis de ambiente antes de tentar IRSA).
> Se a sessão da AWS Academy expirar, atualize esses valores e reinicie os deployments:
>
> ```bash
> AK=$(aws --profile <seu-profile> configure get aws_access_key_id)
> SK=$(aws --profile <seu-profile> configure get aws_secret_access_key)
> ST=$(aws --profile <seu-profile> configure get aws_session_token)
>
> kubectl patch secret evaluation-service-secret -n production --type merge -p \
>   "{\"data\":{\"AWS_ACCESS_KEY_ID\":\"$(printf '%s' "$AK" | base64)\",\"AWS_SECRET_ACCESS_KEY\":\"$(printf '%s' "$SK" | base64)\",\"AWS_SESSION_TOKEN\":\"$(printf '%s' "$ST" | base64)\"}}"
> kubectl patch secret analytics-service-secret -n production --type merge -p \
>   "{\"data\":{\"AWS_ACCESS_KEY_ID\":\"$(printf '%s' "$AK" | base64)\",\"AWS_SECRET_ACCESS_KEY\":\"$(printf '%s' "$SK" | base64)\",\"AWS_SESSION_TOKEN\":\"$(printf '%s' "$ST" | base64)\"}}"
>
> kubectl rollout restart deployment/evaluation-service deployment/analytics-service -n production
> ```
>
> Em uma conta AWS real (fora de lab), prefira recriar o IRSA em vez deste workaround.

Detalhes adicionais (segredos, geração da chave real do `evaluation-service`, migração da
estrutura antiga) estão em [k8s/README.md](k8s/README.md).

## Teste de carga (HPA) com k6

O script em [load_test/hpa-load-test.js](load_test/hpa-load-test.js) gera carga sustentada em
`/evaluation-service/evaluate`, o que também publica eventos no SQS e alimenta o
`analytics-service` — ou seja, um único teste exercita o HPA dos 5 microsserviços. Pré-requisito:
[k6](https://k6.io/docs/get-started/installation/) instalado (`brew install k6`).

### Contra o Minikube (overlay `development`)

O Ingress do Minikube não é acessível diretamente do host sem `sudo`/`minikube tunnel`; a forma
mais simples é expor o `ingress-nginx-controller` via `port-forward`:

```bash
# Terminal 1: mantenha rodando durante todo o teste
kubectl port-forward -n ingress-nginx svc/ingress-nginx-controller 8080:80
```

```bash
# Terminal 2: roda o teste (~4 min: 30s ramp-up, 3min sustentado a 50 VUs, 30s ramp-down)
k6 run -e BASE_URL="http://localhost:8080" load_test/hpa-load-test.js
```

### Contra o EKS (overlay `production`)

Use a URL pública do Load Balancer do `ingress-nginx`:

```bash
INGRESS_HOST=$(kubectl get ingress microservices -n production -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
k6 run -e BASE_URL="http://$INGRESS_HOST" load_test/hpa-load-test.js
```

### Acompanhando o HPA durante o teste

Em outro terminal, observe as réplicas escalando (2 → até 5) e voltando ao mínimo alguns minutos
após o teste terminar (janela padrão de estabilização de scale-down do HPA é de 5 minutos):

```bash
kubectl get hpa -n development -w   # ou -n production
```

Variáveis opcionais do script: `FLAG_NAME` (padrão `demo-flag`) para testar contra uma flag
específica já cadastrada no `flag-service`.
