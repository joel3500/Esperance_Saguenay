# app.py
import os
from pathlib import Path
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for, session, flash)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from models import (init_database, db_proxy, User, Project, Need, Media, ProjectLink, Comment)

# ========================= Comportement de retour èa la ligne ======================================== #
from markupsafe import Markup, escape

# ========================= générer & “envoyer” le code de validation pour un compte ================== # 
import random
import datetime
import smtplib
from email.message import EmailMessage

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

# ================================ Helpers =========================== #
# ... après init_database()
@app.before_request
def _db_connect():
    """Ouvre une connexion DB au début de chaque requête."""
    if db_proxy.is_closed():
        db_proxy.connect(reuse_if_open=True)

@app.teardown_request
def _db_close(exc):
    """Ferme la connexion DB à la fin de chaque requête."""
    if not db_proxy.is_closed():
        db_proxy.close()

# ======================== Fin de l'innitiation de la BD =========================== #

# ================== Validation de compte utilisateur ========================= #
def generate_verification_code() -> str:
    """
    Génère un code à 5 chiffres (string, avec zéros devant si besoin).
    Exemple : '00427'
    """
    return f"{random.randint(0, 99999):05d}"

def send_verification_email(email: str, code: str):
    """
    Envoie (ou simule l'envoi) d'un email de vérification.
    Pour rester simple :
    - si les variables SMTP ne sont pas configurées, on affiche le code dans la console.
    - sinon, on envoie un vrai email via SMTP.
    """

    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    from_email = os.getenv("FROM_EMAIL", smtp_user)

    subject = "Votre code de vérification - Espérance Saguenay"
    body = (
        f"Bonjour,\n\n"
        f"Voici votre code de vérification Espérance Saguenay : {code}\n\n"
        f"Entrez ce code sur la page de vérification pour activer votre compte.\n\n"
        f"- Espérance Saguenay"
    )

    # Si on n'a pas de configuration SMTP, on se contente de l'afficher dans les logs.
    if not (smtp_host and smtp_user and smtp_password and from_email):
        print("=== EMAIL DE VÉRIFICATION (mode console) ===")
        print(f"À : {email}")
        print(f"CODE : {code}")
        print("===========================================")
        return

    # Sinon, tentative d'envoi réel
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = email
        msg.set_content(body)

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        print(f"Email de vérification envoyé à {email}")
    except Exception as exc:
        print("Erreur lors de l'envoi de l'email :", exc)
        print("Code de vérification :", code)

#=============================== Fin de Validation de compte ================== #
def login_required(f):
    # Petit décorateur pour protéger certaines routes
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Vous devez être connecté.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# ==== Comportement pour retours à la ligne.
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

# ----- Seed owner -----
def seed_owner():
    owner_prenom  = "Fehmi"
    owner_nom     = "Jaafar"
    owner_ville   = "La Baie"
    owner_email   = "fjaafar@uqac.ca"
    owner_pwd     = "FJ_prof_uqac_2025"

    u = User.get_or_none(User.email == owner_email.lower())
    if not u:
        User.create(
            prenom=owner_prenom,
            nom=owner_nom,
            ville=owner_ville,
            email=owner_email.lower(),
            password_hash=generate_password_hash(owner_pwd),
            is_owner="yes"
        )

# ON cree l'admin
seed_admin()
# ON cree le Propriétaire
seed_owner()

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

        # Génération du code de vérification
        code = generate_verification_code()
        now = datetime.datetime.now()

        with db_proxy.atomic():
            user = User.create(
                prenom=prenom,
                nom=nom,
                ville=ville,
                email=email,
                password_hash=password_hash,
                is_verified=False,
                verification_code=code,
                verification_created_at=now,
            )

        # Envoi (ou simulation) du mail
        send_verification_email(user.email, code)

        flash(
            "Inscription enregistrée. Un code de vérification a été envoyé à votre email. "
            "Veuillez le saisir pour activer votre compte.",
            "info",
        )
        # On ne le connecte PAS encore : il doit d'abord vérifier son compte
        return redirect(url_for("verify_account", email=user.email))

    return render_template("signup.html")


@app.route("/verify/", methods=["GET", "POST"])
def verify_account():
    # email pré-rempli éventuel (quand on vient juste de s'inscrire)
    prefill_email = request.args.get("email", "").strip().lower()

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        code = request.form.get("code", "").strip()

        if not (email and code):
            flash("Veuillez saisir votre email et le code de vérification.", "warning")
            return redirect(url_for("verify_account", email=email))

        try:
            user = User.get(User.email == email)
        except User.DoesNotExist:
            flash("Aucun compte trouvé avec cet email.", "danger")
            return redirect(url_for("verify_account"))

        if user.is_verified:
            flash("Ce compte est déjà vérifié, vous pouvez vous connecter.", "info")
            return redirect(url_for("login"))

        if user.verification_code != code:
            flash("Code de vérification invalide.", "danger")
            return redirect(url_for("verify_account", email=email))

        # Tout est bon : on active le compte
        user.is_verified = True
        user.verification_code = None
        user.verification_created_at = None
        user.save()

        flash("Votre compte a été vérifié avec succès. Vous pouvez maintenant vous connecter.", "success")
        return redirect(url_for("login"))

    # GET
    return render_template("verify_account.html", prefill_email=prefill_email)


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

        # Vérification du compte
        if not user.is_verified:
            flash(
                "Votre compte n'est pas encore vérifié. "
                "Veuillez saisir le code reçu par email.",
                "warning"
            )
            return redirect(url_for("verify_account", email=user.email))

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
        
        # On récupère la ville du formulaire, sinon on prend la ville de l'utilisateur
        ville_form = request.form.get("ville", "").strip()
        ville = ville_form or current_user.ville

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

# ======================== Modification d'un projet =================================

@app.route("/project/<int:project_id>/edit/", methods=["GET", "POST"])
@login_required
def edit_project(project_id):
    current_user = get_current_user()

    # On récupère le projet
    try:
        project = Project.get_by_id(project_id)
    except Project.DoesNotExist:
        flash("Projet introuvable.", "danger")
        return redirect(url_for("index"))

    # Sécurité : seul le créateur peut modifier son projet
    if project.createur.id != current_user.id:
        flash("Vous ne pouvez modifier que vos propres projets.", "danger")
        return redirect(url_for("project_detail", project_id=project.id))

    if request.method == "POST":
        description = request.form.get("description", "").strip()
        ville_form = request.form.get("ville", "").strip()
        ville = ville_form or current_user.ville

        if not description:
            flash("La description du projet est obligatoire.", "warning")
            return redirect(url_for("edit_project", project_id=project.id))

        with db_proxy.atomic():
            # 1) Mise à jour des champs de base
            project.description = description
            project.ville = ville
            project.save()

            # 2) Mise à jour de la liste des besoins
            Need.delete().where(Need.project == project).execute()
            nouveaux_besoins = request.form.getlist("besoins")
            for b in nouveaux_besoins:
                b = b.strip()
                if b:
                    Need.create(project=project, texte=b)

            # 3) Mise à jour de la liste des liens
            ProjectLink.delete().where(ProjectLink.project == project).execute()
            nouveaux_urls = request.form.getlist("urls")
            for u in nouveaux_urls:
                u = u.strip()
                if u:
                    ProjectLink.create(project=project, url=u)

            # 4) Ajout de nouveaux médias (on garde les anciens)
            files = request.files.getlist("medias")
            save_media_files(files, project)

        flash("Projet mis à jour avec succès.", "success")
        return redirect(url_for("project_detail", project_id=project.id))

    # GET : on réutilise le même formulaire que pour la création
    return render_template("new_project.html", current_user=current_user, project=project)

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

# “Un utilisateur doit pouvoir supprimer son compte.”
# ajouter un lien “Supprimer mon compte” visible uniquement pour un user connecté
# au moment de la suppression, on :
# supprime les projets de cet utilisateur (et ce qui dépend d’eux),
# supprime ses commentaires,
# supprime le compte,
# vide la session.
@app.route("/account/delete/", methods=["GET", "POST"])
@login_required
def delete_account():
    current_user = get_current_user()

    if request.method == "POST":
        # On supprime les données liées à cet utilisateur
        with db_proxy.atomic():
            # 1) Supprimer les commentaires de l'utilisateur
            Comment.delete().where(Comment.auteur == current_user).execute()

            # 2) Supprimer les projets créés par l'utilisateur
            projects = list(Project.select().where(Project.createur == current_user))
            for p in projects:
                # On supprime d'abord tout ce qui dépend du projet
                Need.delete().where(Need.project == p).execute()
                ProjectLink.delete().where(ProjectLink.project == p).execute()
                Media.delete().where(Media.project == p).execute()
                Comment.delete().where(Comment.project == p).execute()
                p.delete_instance()

            # 3) Supprimer l'utilisateur
            current_user.delete_instance()

        # 4) Déconnexion
        session.clear()
        flash("Votre compte et vos projets ont été supprimés.", "info")
        return redirect(url_for("index"))

    # GET : afficher une page de confirmation simple
    return render_template("account_delete.html", current_user=current_user)

# ==================== main ================================== #

if __name__ == "__main__":
    app.run(debug=True)
