# models.py
import datetime
import os
from dotenv import load_dotenv

from peewee import (
    IntegerField, Model, CharField, TextField, DateTimeField, BooleanField,
    ForeignKeyField, DatabaseProxy, SqliteDatabase
)
from playhouse.postgres_ext import PostgresqlExtDatabase
from playhouse.db_url import connect  # important

load_dotenv()

# Proxy : permet de brancher soit Postgres, soit SQLite
db_proxy = DatabaseProxy()


class BaseModel(Model):
    class Meta:
        database = db_proxy


class User(BaseModel):
    prenom = CharField()
    nom = CharField()
    ville = CharField()
    email = CharField(unique=True)
    password_hash = CharField()
    created_at = DateTimeField(default=datetime.datetime.now)

    # Quand un utilisateur s’inscrit → on lui envoie un code à 5 chiffres par email → il doit le saisir pour valider son compte.
    # Un utilisateur peut supprimer son compte.
    is_verified = BooleanField(default=False)           # → compte validé ou non
    verification_code = CharField(null=True)            # → le code 5 chiffres
    verification_created_at = DateTimeField(null=True)  # → quand le code a été généré
    
    # administrateur
    is_admin = BooleanField(default=False)


class Project(BaseModel):
    createur = ForeignKeyField(User, backref="projects")
    description = TextField()
    ville = CharField(null=True)
    created_at = DateTimeField(default=datetime.datetime.now)

    # Nouveau : gestion de statut
    # "pending"   = en attente
    # "validated" = validé et visible sur la page index
    # "archived"  = validé mais caché du grand public
    status = CharField(default="pending")  # valeurs attendues : pending / validated / archived

    # Projet retiré de la liste par l’admin (soft delete)
    deleted_by_admin = BooleanField(default=False)

    # Ajout de quelques compteurs simples dans Project
    comments_count = IntegerField(default=0)
    needs_count = IntegerField(default=0)

    # Statistiques temporelles fines
    validated_at = DateTimeField(null=True)
    archived_at = DateTimeField(null=True)

    visits_count = IntegerField(default=0)

class Need(BaseModel):
    project = ForeignKeyField(Project, backref="needs")
    texte = CharField()

    # Suivi des besoins comblés
    is_fulfilled = BooleanField(default=False)
    fulfilled_at = DateTimeField(null=True)

    # Nouveau : certains besoins sont financiers
    is_money = BooleanField(default=False)       # True = besoin en argent
    amount_goal = IntegerField(null=True)       # montant total souhaité (en dollars par ex.)

class Media(BaseModel):
    project = ForeignKeyField(Project, backref="medias")
    filename = CharField()
    media_type = CharField()  # "image" ou "video"


class ProjectLink(BaseModel):
    project = ForeignKeyField(Project, backref="links")
    url = CharField()


class Comment(BaseModel):
    project = ForeignKeyField(Project, backref="comments")
    auteur = ForeignKeyField(User, backref="comments")
    contenu = TextField()
    parent = ForeignKeyField("self", null=True, backref="replies")
    created_at = DateTimeField(default=datetime.datetime.now)


class Contribution(BaseModel):
    need = ForeignKeyField(Need, backref="contributions")
    user = ForeignKeyField(User, backref="contributions")
    amount = IntegerField()  # montant en dollars (ou en cents si tu préfères)
    created_at = DateTimeField(default=datetime.datetime.now)
    updated_at = DateTimeField(default=datetime.datetime.now)

# ==================== Pour initialiser la Base de données

def init_database():
    """
    Sur Render :
      - si DATABASE_URL est défini -> on se connecte à Postgres (Internal URL)
    En local :
      - si pas de DATABASE_URL -> on utilise SQLite (esperance.db)
    """
    db_url = os.getenv("DATABASE_URL")

    if db_url:
        print("DATABASE_URL détecté, utilisation de PostgreSQL...")
        db = connect(db_url)  # playhouse.db_url.connect
    else:
        print("Aucune DATABASE_URL, utilisation de SQLite (esperance.db).")
        db = SqliteDatabase("esperance.db")

    # On branche le proxy sur cette DB
    db_proxy.initialize(db)

    # On crée les tables une fois, Peewee gère la connexion dans ce bloc
    with db_proxy:
        db_proxy.create_tables(
            [User, Project, Need, Media, ProjectLink, Comment, Contribution]
        )


