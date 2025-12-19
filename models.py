# models.py
import datetime
import os

from peewee import (
    Model, CharField, TextField, DateTimeField,
    ForeignKeyField, DatabaseProxy, SqliteDatabase
)
from playhouse.postgres_ext import PostgresqlExtDatabase
from playhouse.db_url import connect  # important

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


class Project(BaseModel):
    createur = ForeignKeyField(User, backref="projects")
    description = TextField()
    ville = CharField(null=True)
    created_at = DateTimeField(default=datetime.datetime.now)


class Need(BaseModel):
    project = ForeignKeyField(Project, backref="needs")
    texte = CharField()


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
    updated_at = DateTimeField(default=datetime.datetime.now)

# ==================== Pour initialiser la Base de données

def init_database():
    
    #  Sur Render :
    #  - si DATABASE_URL est défini -> on se connecte à Postgres (Internal URL)
    
    #  En local :
    #  - si pas de DATABASE_URL -> on utilise SQLite (esperance.db)
    

    db_url = os.getenv("DATABASE_URL")

    if db_url:
        try:
            print("DATABASE_URL détecté, tentative de connexion PostgreSQL...")
            postgres_db = connect(db_url)  # utilise directement l'URL Render
            postgres_db.connect()
            postgres_db.close()
            print("Connexion PostgreSQL (DATABASE_URL) OK.")
            db_proxy.initialize(postgres_db)
        except Exception as exc:
            print("Erreur PostgreSQL via DATABASE_URL :", exc)
            print("Bascule vers SQLite (esperance.db).")
            sqlite_db = SqliteDatabase("esperance.db")
            db_proxy.initialize(sqlite_db)
    else:
        print("Aucune DATABASE_URL, utilisation de SQLite (esperance.db).")
        sqlite_db = SqliteDatabase("esperance.db")
        db_proxy.initialize(sqlite_db)

    # Création des tables si elles n'existent pas
    with db_proxy:
        db_proxy.create_tables(
            [User, Project, Need, Media, ProjectLink, Comment]
        )

