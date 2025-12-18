# app.py
import os
from pathlib import Path
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for, session, flash)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from models import (init_database, db_proxy, User, Project, Need, Media, ProjectLink, Comment)
# ========================= Comportement de retour èa la ligne ====================
from markupsafe import Markup, escape

# ========================= Configuration de base ==========================

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "static" / "uploads"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".jfif"}
ALLOWED_VIDEO_EXT = {".mp4", ".webm", ".ogg"}

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "sera-changé-en-prod")
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)

# On initialise la base ici, une seule fois au démarrage
init_database()

# ================================ Helpers ===========================

def login_required(f):
    # Petit décorateur pour protéger certaines routes
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Vous devez être connecté.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# ==== Comportement pour retours àa la ligne.
@app.template_filter("nl2br")
def nl2br(value):
    # Transforme les retours à la ligne (\n) en balises <br>
    # tout en échappant le HTML pour éviter les injections.
    
    if not value:
        return ""
    # escape() protège le texte, splitlines() découpe par ligne
    lines = escape(value).splitlines()
    return Markup("<br>".join(lines))

def get_current_user():
    # Retourne l'objet User courant ou None.
    user_id = session.get("user_id")
    if not user_id:
        return None
    try :
        return User.get_by_id(user_id)
    except User.DoesNotExist:
        return None

def save_media_files(files, project):
    # Enregistre les fichiers envoyés pour un projet.
    for f in files:
        if not f or f.filename == "":
            continue
        filename = secure_filename(f.filename)
        suffix = Path(filename).suffix.lower()

        if suffix in ALLOWED_IMAGE_EXT:
            media_type = "image"
        elif suffix in ALLOWED_VIDEO_EXT:
            media_type = "video"
        else:
            # On ignore les extensions non autorisées
            continue

        dest = UPLOAD_FOLDER / filename
        f.save(dest)

        Media.create(
            project=project,
            filename=filename,
            media_type=media_type
        )

# ----- Helpers -----
def current_user():
    uid = session.get("uid")
    if not uid: return None
    try:
        return User.get_by_id(uid)
    except:
        return None

def admin_required():
    u = current_user()
    if not u or u.is_admin != "yes":
        flash("Accès admin requis.")
        return redirect(url_for('index'))

def is_owner_or_admin(owner_user_id):
    u = current_user()
    return u and (u.is_admin == "yes" or (owner_user_id is not None and u.id == owner_user_id))

# ----- Seed admin -----
def seed_admin():
    admin_prenom  = "Joel"
    admin_nom     = "Sandé"
    admin_ville   = "Chicoutimi"
    admin_email   = "docjoel007@gmail.com"
    admin_pwd     = "Episte_Plous2025"
    u = User.get_or_none(User.email == admin_email.lower())
    if not u:
        User.create(
            prenom=admin_prenom,
            nom=admin_nom,
            ville=admin_ville,
            email=admin_email.lower(),
            password_hash=generate_password_hash(admin_pwd),
            is_admin="yes"
        )

seed_admin()
# seed_proprietaire()

# ========================== Routes publiques =================================

@app.route("/")
def index():
    # Page d'accueil : liste des projets.
    projects = (
        Project
        .select()
        .order_by(Project.created_at.desc())
        .join(User)
    )
    current_user = get_current_user()
    return render_template(
        "index.html",
        projects=projects,
        current_user=current_user
    )

@app.route("/vision_et_mission")
def vision_et_mission():
    # Page Notre vision :
    projects = (
        Project
        .select()
        .order_by(Project.created_at.desc())
        .join(User)
    )
    current_user = get_current_user()
    return render_template(
        "vision_et_mission.html",
        projects=projects,
        current_user=current_user
    )


@app.route("/project/<int:project_id>/")
def project_detail(project_id):
    # Page détaillée d'un projet + commentaires.
    try:
        project = Project.get_by_id(project_id)
    except Project.DoesNotExist:
        flash("Projet introuvable.", "danger")
        return redirect(url_for("index"))

    # On précharge commentaires + auteurs
    comments = (
        Comment
        .select()
        .where(Comment.project == project, Comment.parent.is_null())
        .order_by(Comment.created_at.desc())
    )

    current_user = get_current_user()
    return render_template(
        "project_detail.html",
        project=project,
        comments=comments,
        current_user=current_user
    )

# =========================== Authentification =========================

@app.route("/signup/", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        prenom = request.form.get("prenom", "").strip()
        nom = request.form.get("nom", "").strip()
        ville = request.form.get("ville", "").strip()
        email = request.form.get("email", "").strip().lower()
        mot_de_passe = request.form.get("mot_de_passe", "")

        if not (prenom and nom and ville and email and mot_de_passe):
            flash("Tous les champs sont obligatoires.", "warning")
            return redirect(url_for("signup"))

        if User.select().where(User.email == email).exists():
            flash("Cet email est déjà utilisé.", "warning")
            return redirect(url_for("signup"))

        password_hash = generate_password_hash(mot_de_passe)

        with db_proxy.atomic():
            user = User.create(
                prenom=prenom,
                nom=nom,
                ville=ville,
                email=email,
                password_hash=password_hash
            )

        session["user_id"] = user.id
        flash("Inscription réussie, bienvenue!", "success")
        return redirect(url_for("index"))

    return render_template("signup.html")

@app.route("/login/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        mot_de_passe = request.form.get("mot_de_passe", "")

        try:
            user = User.get(User.email == email)
        except User.DoesNotExist:
            flash("Identifiants invalides.", "danger")
            return redirect(url_for("login"))

        if not check_password_hash(user.password_hash, mot_de_passe):
            flash("Identifiants invalides.", "danger")
            return redirect(url_for("login"))

        session["user_id"] = user.id
        flash("Connexion réussie.", "success")
        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/logout/")
def logout():
    session.clear()
    flash("Vous êtes déconnecté.", "info")
    return redirect(url_for("index"))

# ======================== Création d'un projet =================================

@app.route("/projects/new/", methods=["GET", "POST"])
@login_required
def new_project():
    current_user = get_current_user()

    if request.method == "POST":
        description = request.form.get("description", "").strip()
        ville = request.form.get("ville", "").strip()

        if not description:
            flash("La description du projet est obligatoire.", "warning")
            return redirect(url_for("new_project"))

        with db_proxy.atomic():
            project = Project.create(
                createur=current_user,
                description=description,
                ville=ville,
            )

            # Liste des besoins (plusieurs inputs avec le même name="besoins")
            besoins = request.form.getlist("besoins")
            for b in besoins:
                b = b.strip()
                if b:
                    Need.create(project=project, texte=b)

            # Liste des liens URL
            urls = request.form.getlist("urls")
            for u in urls:
                u = u.strip()
                if u:
                    ProjectLink.create(project=project, url=u)

            # Upload des médias
            files = request.files.getlist("medias")
            save_media_files(files, project)

        flash("Projet créé avec succès.", "success")
        return redirect(url_for("project_detail", project_id=project.id))

    return render_template("new_project.html", current_user=current_user)


# ==================== Commentaires & réponses =====================

@app.route("/project/<int:project_id>/comment/", methods=["POST"])
def add_comment(project_id):
    current_user = get_current_user()
    contenu = request.form.get("contenu", "").strip()
    parent_id = request.form.get("parent_id")

    if not contenu:
        flash("Le commentaire ne peut pas être vide.", "warning")
        return redirect(url_for("project_detail", project_id=project_id))

    try:
        project = Project.get_by_id(project_id)
    except Project.DoesNotExist:
        flash("Projet introuvable.", "danger")
        return redirect(url_for("index"))

    parent = None
    if parent_id:
        try:
            parent = Comment.get_by_id(int(parent_id))
        except Comment.DoesNotExist:
            parent = None

    Comment.create(
        project=project,
        auteur=current_user,
        contenu=contenu,
        parent=parent
    )

    flash("Commentaire ajouté.", "success")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/comment/<int:comment_id>/edit/", methods=["GET", "POST"])
def edit_comment(comment_id):
    current_user = get_current_user()
    try:
        comment = Comment.get_by_id(comment_id)
    except Comment.DoesNotExist:
        flash("Commentaire introuvable.", "danger")
        return redirect(url_for("index"))

    if comment.auteur.id != current_user.id:
        flash("Vous ne pouvez modifier que vos propres commentaires.", "danger")
        return redirect(url_for("project_detail", project_id=comment.project.id))

    if request.method == "POST":
        new_content = request.form.get("contenu", "").strip()
        if not new_content:
            flash("Le commentaire ne peut pas être vide.", "warning")
            return redirect(url_for("edit_comment", comment_id=comment_id))

        comment.contenu = new_content
        comment.updated_at = Comment.updated_at.default()  # now
        comment.save()

        flash("Commentaire modifié.", "success")
        return redirect(url_for("project_detail", project_id=comment.project.id))

    return render_template(
        "edit_comment.html",
        comment=comment,
        current_user=current_user
    )


@app.route("/comment/<int:comment_id>/delete/", methods=["POST"])
def delete_comment(comment_id):
    current_user = get_current_user()

    try:
        comment = Comment.get_by_id(comment_id)
    except Comment.DoesNotExist:
        flash("Commentaire introuvable.", "danger")
        return redirect(url_for("index"))

    if comment.auteur.id != current_user.id:
        flash("Vous ne pouvez supprimer que vos propres commentaires.", "danger")
        return redirect(url_for("project_detail", project_id=comment.project.id))

    project_id = comment.project.id
    comment.delete_instance(recursive=True)  # supprime aussi les réponses

    flash("Commentaire supprimé.", "info")
    return redirect(url_for("project_detail", project_id=project_id))

# ==================== main ================================== #

if __name__ == "__main__":
    app.run(debug=True)
