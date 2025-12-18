# models.py
import datetime
import os

from peewee import (
    Model, CharField, TextField, DateTimeField,
    ForeignKeyField, DatabaseProxy, SqliteDatabase
)
from playhouse.postgres_ext import PostgresqlExtDatabase

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

    # Essaie d'abord de se connecter à PostgreSQL.
    # Si échec, bascule automatiquement vers SQLite.

    # ============= Variables d'environnement pour Postgres (pour Render)

    pg_db_name = os.getenv("POSTGRES_DB", "esperance_db")
    pg_user = os.getenv("POSTGRES_USER", "postgres")
    pg_password = os.getenv("POSTGRES_PASSWORD", "")
    pg_host = os.getenv("POSTGRES_HOST", "localhost")
    pg_port = int(os.getenv("POSTGRES_PORT", "5432"))

    try:
        postgres_db = PostgresqlExtDatabase(
            pg_db_name,
            user=pg_user,
            password=pg_password,
            host=pg_host,
            port=pg_port,
        )
        postgres_db.connect()
        postgres_db.close()
        print("Base PostgreSQL OK, utilisation de PostgreSQL.")
        db_proxy.initialize(postgres_db)
    except Exception as exc:
        print("Impossible de se connecter à PostgreSQL :", exc)
        print("Bascule vers SQLite (esperance.db).")
        sqlite_db = SqliteDatabase("esperance.db")
        db_proxy.initialize(sqlite_db)

    # ================== Création des tables si elles n'existent pas

    with db_proxy:
         db_proxy.create_tables(
             [User, Project, Need, Media, ProjectLink, Comment]
        )
