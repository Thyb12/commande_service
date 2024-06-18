import pika
import os
import time

RABBITMQ_HOST = os.environ.get('RABBITMQ_HOST', 'localhost')
RABBITMQ_QUEUE = os.environ.get('RABBITMQ_QUEUE', 'commande_queue')

def connect_and_publish():
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(host=RABBITMQ_HOST))
    channel = connection.channel()
    channel.queue_declare(queue=RABBITMQ_QUEUE)

    try:
        while True:
            message = 'Hello, RabbitMQ!'
            channel.basic_publish(exchange='',
                                  routing_key=RABBITMQ_QUEUE,
                                  body=message)
            print(f'Sent message: {message}')
            time.sleep(0.1)  # Envoyer un message toutes les 5 secondes
    except KeyboardInterrupt:
        print('Interrupted')
    finally:
        connection.close()

if __name__ == "__main__":
    connect_and_publish()
