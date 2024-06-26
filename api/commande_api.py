import os
import httpx
from fastapi import FastAPI, HTTPException, Depends, Request, Response
from pydantic import BaseModel
from typing import List, Optional
from pymongo import MongoClient
from bson import ObjectId
from prometheus_client import Summary, Counter, generate_latest, CONTENT_TYPE_LATEST
import logging
import pika
from datetime import datetime, timedelta

logger = logging.getLogger("uvicorn.error")

# Création de l'instance FastAPI pour initialiser l'application et permettre la définition des routes.
app = FastAPI()

# Configuration et mise en place de la connexion à la base de données avec MongoDB
MONGODB_URL = "mongodb://localhost:27017"
DATABASE_NAME = "MSPR_1"
COLLECTION_NAME = "commandes"
RABBITMQ_HOST = "localhost"
RABBITMQ_QUEUE = "commande_queue"
client = MongoClient(MONGODB_URL)
db = client[DATABASE_NAME]
collection = db[COLLECTION_NAME]

# Création d'un modèle pydantic pour la création de commande
class CommandeCreate(BaseModel):
    name: str
    quantity: int
    createdAt: datetime
    customer: str 
    produits: List[str]
# Création d'un modèle pydantic pour la réponse de commande
class CommandeResponse(CommandeCreate):
    id: str

    class Config:
        orm_mode = True
        arbitrary_types_allowed = True

# Définir des métriques Prometheus
REQUEST_TIME = Summary('request_processing_seconds', 'Time spent processing request')
REQUEST_COUNT = Counter('request_count', 'Total count of requests')


# Fonction pour récupérer les produits à partir de l'API produit
async def fetch_products(product_ids: List[str]) -> List[dict]:
    produits = []
    async with httpx.AsyncClient() as client:
        for product_id in product_ids:
            response = await client.get(f"http://localhost:8888/produit/{product_id}")
            if response.status_code == 200:
                produits.append(response.json())
            else:
                raise HTTPException(status_code=404, detail=f"Produit {product_id} not found")
    return produits

# Fonction pour récupérer les clients à partir de l'API client
async def fetch_clients(client_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://localhost:8887/client/{client_id}")
        if response.status_code == 200:
            return response.json()
        else:
            raise HTTPException(status_code=404, detail=f"Client {client_id} not found")

# Middleware pour mesurer le temps de traitement des requêtes
@app.middleware("http")
async def add_prometheus_metrics(request: Request, call_next):
    with REQUEST_TIME.time():
        response = await call_next(request)
        REQUEST_COUNT.inc()
    return response

# Route pour exposer les métriques
@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

def connect_rabbitmq():
    try:
        parameters = pika.ConnectionParameters(RABBITMQ_HOST)
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        channel.queue_declare(queue=RABBITMQ_QUEUE)
        return channel
    except pika.exceptions.AMQPConnectionError as e:
        logger.error(f"Failed to connect to RabbitMQ: {e}")
        raise HTTPException(status_code=500, detail="Could not connect to RabbitMQ")

failed_attempts = {}

# Fonction pour vérifier et limiter les tentatives de connexion
def rate_limiting(ip_address: str):
    now = datetime.now()
    if ip_address in failed_attempts:
        attempt_info = failed_attempts[ip_address]
        last_attempt_time = attempt_info["timestamp"]
        attempts = attempt_info["count"]
        logger.info(f"IP {ip_address}: {attempts} attempts, last attempt at {last_attempt_time}")
        # Si moins de 60 secondes depuis la dernière tentative, augmenter le compteur de tentatives
        if now - last_attempt_time < timedelta(seconds=60):
            attempts += 1
            failed_attempts[ip_address] = {"count": attempts, "timestamp": now}
            # Si plus de 5 tentatives dans les 60 secondes, déclencher la limitation
            if attempts > 5:
                raise HTTPException(status_code=429, detail="Too many requests. Try again later.")
        else:
            # Réinitialiser après 60 secondes
            failed_attempts[ip_address] = {"count": 1, "timestamp": now}
    else:
        failed_attempts[ip_address] = {"count": 1, "timestamp": now}
    logger.info(f"IP {ip_address}: allowed")

@app.post("/commandes/create", response_model=CommandeResponse)
async def create_commande(commande: CommandeCreate, request: Request):
    client_ip = request.client.host
    rate_limiting(client_ip)  # Limiter les tentatives de connexion par adresse IP

    # Récupérer les produits avant de créer la commande
    produits = await fetch_products(commande.produits)
    # Récupérer les informations du client
    client_info = await fetch_clients(commande.customer)
    if not client_info:
        raise HTTPException(status_code=404, detail="Client not found")
    
    commande_data = commande.dict()
    commande_data["produits"] = produits
    commande_data["customer"] = client_info
    commande_data["createdAt"] = datetime.utcnow()
    result = collection.insert_one(commande_data)
    commande_data["id"] = str(result.inserted_id)

    if os.getenv("ENV") == "prod":
        try:
            # Envoyer un message à RabbitMQ
            channel = connect_rabbitmq()
            message = f"Commande créée: {commande.name} avec quantité: {commande.quantity}"
            channel.basic_publish(exchange='', routing_key=RABBITMQ_QUEUE, body=message)
            channel.close()
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi du message RabbitMQ : {e}")
            raise HTTPException(status_code=500, detail="Erreur interne du serveur")

    return commande_data
# Route GET pour voir toutes les commandes
@app.get("/commandes/all", response_model=List[CommandeResponse])
async def read_commandes(skip: int = 0, limit: int = 10):
    commandes = list(collection.find().skip(skip).limit(limit))
    for commande in commandes:
        commande["id"] = str(commande["_id"])
        del commande["_id"]
    return commandes

# Route DELETE pour supprimer une commande par son id
@app.delete("/commandes/{commande_id}")
async def delete_commande(request: Request, commande_id: str):
    client_ip = request.client.host
    rate_limiting(client_ip)  # Limiter les tentatives de connexion par adresse IP

    result = collection.delete_one({"_id": ObjectId(commande_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Commande not found")
    return {"detail": "Commande deleted"}

# Route GET pour voir une commande spécifique par son id
@app.get("/commande/{commande_id}", response_model=CommandeResponse)
async def read_specific_commande(commande_id: str):
    commande = collection.find_one({"_id": ObjectId(commande_id)})
    if commande is None:
        raise HTTPException(status_code=404, detail="Commande not found")
    commande["id"] = str(commande["_id"])
    del commande["_id"]
    return commande

# Route PUT pour mettre à jour une commande par son id
@app.put("/commandes/{commande_id}", response_model=CommandeResponse)
async def update_commande(commande_id: str, commande: CommandeCreate, request: Request):
    client_ip = request.client.host
    rate_limiting(client_ip)  # Limiter les tentatives de connexion par adresse IP

    # Récupérer les informations du client
    client_info = await fetch_clients(commande.customer)
    if not client_info:
        raise HTTPException(status_code=404, detail="Client not found")

    update_data = commande.dict()
    update_data["customer"] = client_info
    result = collection.update_one({"_id": ObjectId(commande_id)}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Commande not found")

    commande = collection.find_one({"_id": ObjectId(commande_id)})
    commande["id"] = str(commande["_id"])
    del commande["_id"]
    return commande