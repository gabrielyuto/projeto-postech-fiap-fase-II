import os
import sys
import threading
import json
import uuid
import time
import logging
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from flask import Flask, jsonify
from dotenv import load_dotenv

# Configura o logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# Carrega .env para desenvolvimento local
load_dotenv()

# --- Configuração geral (não depende de ambiente) ---
APP_ENV = os.getenv("APP_ENV", "production").lower()

AWS_REGION = os.getenv("AWS_REGION")
AWS_SQS_URL = os.getenv("AWS_SQS_URL")
AWS_DYNAMODB_TABLE_NAME = os.getenv("AWS_DYNAMODB_TABLE")

def build_aws_clients():
    if APP_ENV == "development":
        AWS_SQS_ENDPOINT_URL = os.getenv("AWS_SQS_ENDPOINT_URL")
        AWS_DYNAMODB_ENDPOINT_URL = os.getenv("AWS_DYNAMODB_ENDPOINT_URL")

        if not all([AWS_REGION, AWS_SQS_ENDPOINT_URL, AWS_DYNAMODB_ENDPOINT_URL, AWS_SQS_URL, AWS_DYNAMODB_TABLE_NAME]):
            log.critical("Erro: variáveis obrigatórias para ambiente de DESENVOLVIMENTO não definidas.")
            sys.exit(1)

        session = boto3.Session(
            region_name=AWS_REGION,
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "fake"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "fake"),
            aws_session_token=os.getenv("AWS_SESSION_TOKEN", "fake"),
        )

        sqs_client = session.client("sqs", endpoint_url=AWS_SQS_ENDPOINT_URL)
        dynamodb_client = session.client("dynamodb", endpoint_url=AWS_DYNAMODB_ENDPOINT_URL)

        return sqs_client, dynamodb_client

    else:
        if not all([AWS_REGION, AWS_SQS_URL, AWS_DYNAMODB_TABLE_NAME]):
            log.critical("Erro: variáveis obrigatórias para ambiente de PRODUÇÃO não definidas.")
            sys.exit(1)

        session = boto3.Session(region_name=AWS_REGION)

        sqs_client = session.client("sqs")
        dynamodb_client = session.client("dynamodb")
        
        return sqs_client, dynamodb_client


def create_clients():
    try:
        sqs_client, dynamodb_client = build_aws_clients()

        log.info(f"Clientes Boto3 inicializados na região {AWS_REGION}")

        return sqs_client, dynamodb_client
    except NoCredentialsError:
        log.critical("Credenciais da AWS não encontradas. Verifique seu ambiente.")
        sys.exit(1)
    except Exception as e:
        log.critical(f"Erro ao inicializar o Boto3: {e}")
        sys.exit(1)


# --- SQS Worker ---

def process_message(message):
    """ Processa uma única mensagem SQS e a insere no DynamoDB """
    sqs_client, dynamodb_client = create_clients()

    try:
        log.info(f"Processando mensagem ID: {message['MessageId']}")
        body = json.loads(message['Body'])
        
        # Gera um ID único para o item no DynamoDB
        event_id = str(uuid.uuid4())
        
        # Constrói o item no formato do DynamoDB
        item = {
            'event_id': {'S': event_id},
            'user_id': {'S': body['user_id']},
            'flag_name': {'S': body['flag_name']},
            'result': {'BOOL': body['result']},
            'timestamp': {'S': body['timestamp']}
        }
        
        # Insere no DynamoDB
        dynamodb_client.put_item(
            TableName=AWS_DYNAMODB_TABLE_NAME,
            Item=item
        )
        
        log.info(f"Evento {event_id} (Flag: {body['flag_name']}) salvo no DynamoDB.")
        
        # Se tudo deu certo, deleta a mensagem da fila
        sqs_client.delete_message(
            QueueUrl=AWS_SQS_URL,
            ReceiptHandle=message['ReceiptHandle']
        )
        
    except json.JSONDecodeError:
        log.error(f"Erro ao decodificar JSON da mensagem ID: {message['MessageId']}")
        # Não deleta a mensagem, pode ser uma "poison pill"
    except ClientError as e:
        log.error(f"Erro do Boto3 (DynamoDB ou SQS) ao processar {message['MessageId']}: {e}")
        # Não deleta a mensagem, tenta novamente
    except Exception as e:
        log.error(f"Erro inesperado ao processar {message['MessageId']}: {e}")
        # Não deleta a mensagem, tenta novamente

def sqs_worker_loop():
    """ Loop principal do worker que ouve a fila SQS """
    log.info("Iniciando o worker SQS...")

    sqs_client, _ = create_clients()

    while True:
        try:
            # Long-polling: espera até 20s por mensagens
            response = sqs_client.receive_message(
                QueueUrl=AWS_SQS_URL,
                MaxNumberOfMessages=10,  # Processa em lotes de até 10
                WaitTimeSeconds=20
            )
            
            messages = response.get('Messages', [])
            if not messages:
                # Nenhuma mensagem, continua o loop
                continue
                
            log.info(f"Recebidas {len(messages)} mensagens.")
            
            for message in messages:
                process_message(message)
                
        except ClientError as e:
            log.error(f"Erro do Boto3 no loop principal do SQS: {e}")
            time.sleep(10) # Pausa antes de tentar novamente
        except Exception as e:
            log.error(f"Erro inesperado no loop principal do SQS: {e}")
            time.sleep(10)

# --- Servidor Flask (Apenas para Health Check) ---

app = Flask(__name__)

@app.route('/health')
def health():
    # Uma verificação de saúde real poderia checar a conexão com o DynamoDB/SQS
    return jsonify({"status": "ok"})

# --- Inicialização ---

def start_worker():
    """ Inicia o worker SQS em uma thread separada """
    worker_thread = threading.Thread(target=sqs_worker_loop, daemon=True)
    worker_thread.start()

# Inicia o worker SQS em uma thread de background
# Isso garante que ele inicie tanto com 'flask run' quanto com 'gunicorn'
start_worker()

if __name__ == '__main__':
    port = int(os.getenv("PORT", 8005))
    app.run(host='0.0.0.0', port=port, debug=False)