Feature: Gestion des commandes dans l'API

  Scenario: Créer un nouveau commande
    Given je crée un commande avec le nom "1commande" et la quantité 10
    Then le commande est créé

  Scenario: Récupérer tous les commandes
    Given je crée un commande avec le nom "2commande" et la quantité 10
    And je crée un commande avec le nom "2.1commande" et la quantité 10
    And je crée un commande avec le nom "2.3commande" et la quantité 10
    Then je reçois une liste de commandes

  Scenario: Supprimer un commande existant
    Given je crée un commande avec le nom "3commande" et la quantité 10
    When je supprime le commande avec l'ID 1
    Then le commande est supprimé avec succès

  Scenario: Récupérer un commande spécifique par son ID
    Given je crée un commande avec le nom "4commande" et la quantité 10
    Then je reçois le commande spécifique avec l'ID 1

  Scenario: Vérifier l'envoi d'un message RabbitMQ lors de la création d'un commande
    Given je crée un commande avec le nom "5commande" et la quantité 10
    Then un message RabbitMQ est envoyé avec les détails du commande "5commande" 10
