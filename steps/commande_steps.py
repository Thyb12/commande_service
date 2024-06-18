import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from behave import given, when, then
from api.commande_api import create_commande, read_commandes, delete_commande, read_specific_commande
from unittest.mock import patch

# Configuration de la base de données en fonction de la variable d'environnement ENV
if os.environ.get("ENV") == "test":
    DATABASE_URL = "sqlite:///./test_db.sqlite"
else:
    DATABASE_URL = "sqlite:///./commande_api.db"

# Créez une session de base de données
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Initialisez la session de base de données pour les tests
@pytest.fixture(scope="function")
def db():
    db = SessionLocal()
    yield db
    db.close()

@given('je crée un commande avec le nom "{name}" et la quantité {quantity:d}')
async def create_product(context, name, quantity):
    commande_data = {"name": name, "quantity": quantity}
    context.commande_created = await create_commande(commande_data, db())


@then('je récupère tous les commandes')
async def get_all_products(context):
    context.commandes = await read_commandes(db())

@when('je supprime le commande avec l\'ID {product_id:d}')
async def delete_product(context, product_id):
    await delete_commande(product_id, db())


@then('le commande est créé')
def check_product_created(context):
    assert read_commandes().__sizeof__() > 0

@then('je reçois une liste de commandes')
async def check_products_received(context):
    reponse = await read_commandes(db())
    assert reponse == context.commandes

@then('le commande est supprimé avec succès')
async def check_product_deleted(context):
    assert await delete_commande(context.commandes[0], db()) is not None
@then('je reçois le commande spécifique avec l\'ID {product_id:d}')
async def check_specific_product_received(context, product_id):
    assert read_specific_commande(product_id) == context.commandes[0]

@then('un message RabbitMQ est envoyé avec les détails du commande "{name} {quantity}')
@patch('api.commande_api.connect_rabbitmq')
async def check_rabbitmq_message_sent(mock_connect_rabbitmq, name, quantity):
    mock_channel = mock_connect_rabbitmq.return_value
    mock_channel.basic_get.return_value = (None, None, f"commande créé: {name} avec quantité: {quantity}".encode('utf-8'))

    await create_commande( commande={"name": name, "quantity": quantity}, db=db())

    mock_connect_rabbitmq.assert_called_once()
    mock_channel.basic_publish.assert_called_once_with(exchange='', routing_key='commande_queue', body=f"commande créé: {name} avec quantité: {context.commande_created.quantity}")
