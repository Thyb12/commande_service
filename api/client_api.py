import os
from fastapi import FastAPI, HTTPException, Depends, Request, Response
from pydantic import BaseModel
from typing import List
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from prometheus_client import Summary, Counter, generate_latest, CONTENT_TYPE_LATEST
import pika
import logging

logger = logging.getLogger("uvicorn.error")

# Création de l'instance FastAPI pour initialiser l'application et permettre la définition des routes.
app = FastAPI()

# Configuration et mise en place de la connexion à la base de données avec SQLAlchemy
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commande_api.db")
DATABASE_URL_TEST = "sqlite:///./test_db.sqlite"
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "commande_queue")

def get_engine(env: str = "prod"):
    if env == "test":
        return create_engine(DATABASE_URL_TEST)
    else:
        return create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# Définition d'une fonction pour obtenir une session de base de données en fonction de l'environnement
def get_db(env: str = "prod"):
    engine = get_engine(env)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    if env == "prod":
        Base.metadata.create_all(bind=engine)
    try:
        yield db
    finally:
        db.close()

# Définition d'un modèle de données pour une commande dans la base de données
Base = declarative_base()

class Commande(Base):
    __tablename__ = "commande"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    quantity = Column(Integer, index=True)

# Création d'un modèle pydantic pour la création de commande
class CommandeCreate(BaseModel):
    name: str
    quantity: int

# Création d'un modèle pydantic pour la réponse de commande
class CommandeResponse(CommandeCreate):
    id: int

    class Config:
        orm_mode = True

# Définir des métriques Prometheus
REQUEST_TIME = Summary('request_processing_seconds', 'Time spent processing request')
REQUEST_COUNT = Counter('request_count', 'Total count of requests')

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


# Route POST pour créer une nouvelle commande dans l'API
@app.post("/commandes/create", response_model=CommandeResponse)
async def create_commande(commande: CommandeCreate, db: Session = Depends(get_db)):
    db_commande = Commande(name=commande.name, quantity=commande.quantity)
    db.add(db_commande)
    db.commit()
    db.refresh(db_commande)
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

    return db_commande

# Route GET pour voir toutes les commandes
@app.get("/commandes/all", response_model=List[CommandeResponse])
async def read_commandes(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    commandes = db.query(Commande).offset(skip).limit(limit).all()
    return commandes

# Route DELETE pour supprimer une commande par son id
@app.delete("/commandes/{commande_id}")
async def delete_commande(commande_id: int, db: Session = Depends(get_db)):
    db_commande = db.query(Commande).filter(Commande.id == commande_id).first()
    if db_commande is None:
        raise HTTPException(status_code=404, detail="Commande not found")
    db.delete(db_commande)
    db.commit()
    return {"detail": "Commande deleted"}

# Route GET pour voir une commande spécifique par son id
@app.get("/commande/{commande_id}", response_model=CommandeResponse)
async def read_specific_commande(commande_id: int, db: Session = Depends(get_db)):
    db_commande = db.query(Commande).filter(Commande.id == commande_id).first()
    if db_commande is None:
        raise HTTPException(status_code=404, detail="Commande not found")
    return db_commande
