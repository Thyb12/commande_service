import pika
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn.error")

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "commande_queue")

def consume_messages():
    try:
        logger.info(f"Connecting to RabbitMQ at {RABBITMQ_HOST}")
        parameters = pika.ConnectionParameters(host=RABBITMQ_HOST)
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        logger.info(f"Connected to RabbitMQ, declaring queue: {RABBITMQ_QUEUE}")
        channel.queue_declare(queue=RABBITMQ_QUEUE)

        def callback(ch, method, properties, body):
            logger.info(f"Received message: {body}")
            # Ajouter votre logique de traitement ici

        channel.basic_consume(queue=RABBITMQ_QUEUE, on_message_callback=callback, auto_ack=True)
        logger.info(f"Consumer started for queue: {RABBITMQ_QUEUE}")
        channel.start_consuming()

    except pika.exceptions.AMQPConnectionError as e:
        logger.error(f"Failed to connect to RabbitMQ: {e}")
        raise

if __name__ == "__main__":
    consume_messages()
