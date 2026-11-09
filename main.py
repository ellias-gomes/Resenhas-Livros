import hashlib
import os
import secrets
import socket
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, Header, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import or_, func
from sqlalchemy.orm import Session, joinedload

from database import engine, get_db, Base
import models
import schemas
import skoob_importer

# Cria todas as tabelas automaticamente no SQLite local
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Entrelinhas & Telas — Rede Social de Resenhas",
    description="Rede social doméstica em tons pastéis para resenhas de livros, filmes e séries com integração Skoob.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)


# ==========================================
# Utilitários de Senha e Autenticação
# ==========================================
def hash_password(password: str, salt: Optional[str] = None) -> str:
    if not salt:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    if "$" not in stored_hash:
        return False
    salt, _ = stored_hash.split("$", 1)
    return secrets.compare_digest(hash_password(password, salt), stored_hash)


def get_optional_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Optional[models.User]:
    if not authorization:
        return None
    token_str = authorization.replace("Bearer ", "").strip()
    if not token_str:
        return None
    token_obj = db.query(models.SessionToken).filter(models.SessionToken.token == token_str).first()
    return token_obj.user if token_obj else None


def get_current_user(
    user: Optional[models.User] = Depends(get_optional_user),
) -> models.User:
    if not user:
        raise HTTPException(status_code=401, detail="Faça login para realizar esta ação.")
    return user


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def serialize_review(
    review: models.Review,
    current_user_id: Optional[int],
    reposts_map: dict[int, int],
) -> schemas.ReviewResponse:
    likes_count = len(review.likes)
    liked_by_me = any(lk.user_id == current_user_id for lk in review.likes) if current_user_id else False
    comments_list = [schemas.CommentResponse.model_validate(c) for c in review.comments]
    orig_snippet = None
    if review.original_review:
        orig_snippet = schemas.OriginalReviewSnippet.model_validate(review.original_review)

    return schemas.ReviewResponse(
        id=review.id,
        user_id=review.user_id,
        category=review.category,
        work_title=review.work_title,
        work_creator=review.work_creator or "",
        work_genre=review.work_genre or "",
        work_year=review.work_year or "",
        cover_url=review.cover_url or "",
        rating=review.rating,
        status=review.status,
        title=review.title or "",
        content=review.content or "",
        has_spoiler=bool(review.has_spoiler),
        is_favorite=bool(review.is_favorite),
        finished_at=review.finished_at or "",
        original_review_id=review.original_review_id,
        repost_comment=review.repost_comment or "",
        skoob_book_id=review.skoob_book_id,
        skoob_url=review.skoob_url,
        created_at=review.created_at,
        updated_at=review.updated_at,
        author=schemas.UserBrief.model_validate(review.author),
        original_review=orig_snippet,
        likes_count=likes_count,
        liked_by_me=liked_by_me,
        reposts_count=reposts_map.get(review.id, 0),
        comments_count=len(comments_list),
        comments=comments_list,
    )


# ==========================================
# Rotas de Rede Doméstica & Sistema
# ==========================================
@app.get("/api/network-info")
def network_info():
    ip = get_local_ip()
    return {
        "local_ip": ip,
        "port": 8000,
        "lan_url": f"http://{ip}:8000",
        "status": "online",
    }


# ==========================================
# Rotas de Autenticação & Usuários
# ==========================================
@app.post("/api/auth/register", response_model=schemas.AuthResponse)
def register(payload: schemas.UserRegister, db: Session = Depends(get_db)):
    clean_username = payload.username.strip().lower().replace(" ", "_")
    clean_email = payload.email.strip().lower()

    existing = (
        db.query(models.User)
        .filter(or_(models.User.username == clean_username, models.User.email == clean_email))
        .first()
    )
    if existing:
        if existing.username == clean_username:
            raise HTTPException(status_code=400, detail="Este nome de usuário já está em uso.")
        raise HTTPException(status_code=400, detail="Este e-mail já está cadastrado.")

    new_user = models.User(
        username=clean_username,
        display_name=payload.display_name.strip(),
        email=clean_email,
        password_hash=hash_password(payload.password),
        bio=(payload.bio or "").strip(),
        avatar_emoji=payload.avatar_emoji or "🌸",
        avatar_color=payload.avatar_color or "#d8b4f8",
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token_str = secrets.token_urlsafe(32)
    db.add(models.SessionToken(token=token_str, user_id=new_user.id))
    db.commit()

    return schemas.AuthResponse(token=token_str, user=schemas.UserBrief.model_validate(new_user))


@app.post("/api/auth/login", response_model=schemas.AuthResponse)
def login(payload: schemas.UserLogin, db: Session = Depends(get_db)):
    identifier = payload.login.strip().lower()
    user = (
        db.query(models.User)
        .filter(or_(models.User.username == identifier, models.User.email == identifier))
        .first()
    )
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Usuário/e-mail ou senha incorretos.")

    token_str = secrets.token_urlsafe(32)
    db.add(models.SessionToken(token=token_str, user_id=user.id))
    db.commit()

    return schemas.AuthResponse(token=token_str, user=schemas.UserBrief.model_validate(user))


@app.post("/api/auth/logout")
def logout(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if authorization:
        token_str = authorization.replace("Bearer ", "").strip()
        db.query(models.SessionToken).filter(models.SessionToken.token == token_str).delete()
        db.commit()
    return {"message": "Logout realizado com sucesso."}


@app.get("/api/auth/me", response_model=schemas.UserBrief)
def get_me(current_user: models.User = Depends(get_current_user)):
    return schemas.UserBrief.model_validate(current_user)


@app.put("/api/users/me", response_model=schemas.UserBrief)
def update_profile(
    payload: schemas.UserUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.display_name is not None and payload.display_name.strip():
        current_user.display_name = payload.display_name.strip()
    if payload.bio is not None:
        current_user.bio = payload.bio.strip()
    if payload.avatar_emoji is not None:
        current_user.avatar_emoji = payload.avatar_emoji
    if payload.avatar_color is not None:
        current_user.avatar_color = payload.avatar_color
    if payload.avatar_url is not None:
        current_user.avatar_url = payload.avatar_url.strip() or None
    if payload.skoob_id is not None:
        current_user.skoob_id = payload.skoob_id.strip() or None

    db.commit()
    db.refresh(current_user)
    return schemas.UserBrief.model_validate(current_user)


@app.get("/api/users")
def list_users(db: Session = Depends(get_db)):
    users = db.query(models.User).order_by(models.User.created_at.asc()).all()
    result = []
    for u in users:
        reviews = [r for r in u.reviews if r.original_review_id is None]
        books_count = sum(1 for r in reviews if r.category == "livro")
        movies_count = sum(1 for r in reviews if r.category == "filme")
        series_count = sum(1 for r in reviews if r.category == "serie")
        favorites_count = sum(1 for r in reviews if r.is_favorite)
        result.append(
            {
                "user": schemas.UserBrief.model_validate(u),
                "stats": {
                    "total_reviews": len(reviews),
                    "livros": books_count,
                    "filmes": movies_count,
                    "series": series_count,
                    "favoritos": favorites_count,
                },
            }
        )
    return result


# ==========================================
# Rotas de Resenhas, Feed, Likes, Comentários e Republicações
# ==========================================
@app.get("/api/reviews", response_model=List[schemas.ReviewResponse])
def list_reviews(
    category: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    user_id: Optional[int] = Query(default=None),
    favorites_only: bool = Query(default=False),
    search: Optional[str] = Query(default=None),
    sort: str = Query(default="recent"),
    current_user: Optional[models.User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    q = (
        db.query(models.Review)
        .options(
            joinedload(models.Review.author),
            joinedload(models.Review.likes),
            joinedload(models.Review.comments).joinedload(models.Comment.author),
            joinedload(models.Review.original_review).joinedload(models.Review.author),
        )
    )

    if category and category != "todos":
        q = q.filter(models.Review.category == category)
    if status and status != "todos":
        q = q.filter(models.Review.status == status)
    if user_id is not None:
        q = q.filter(models.Review.user_id == user_id)
    if favorites_only:
        q = q.filter(models.Review.is_favorite.is_(True))
    if search and search.strip():
        term = f"%{search.strip()}%"
        q = q.filter(
            or_(
                models.Review.work_title.ilike(term),
                models.Review.work_creator.ilike(term),
                models.Review.title.ilike(term),
                models.Review.content.ilike(term),
                models.Review.work_genre.ilike(term),
            )
        )

    if sort == "rating_desc":
        q = q.order_by(models.Review.rating.desc(), models.Review.created_at.desc())
    elif sort == "oldest":
        q = q.order_by(models.Review.created_at.asc())
    else:
        q = q.order_by(models.Review.created_at.desc())

    reviews = q.all()

    # Mapa de contagem de republicações
    repost_counts = dict(
        db.query(models.Review.original_review_id, func.count(models.Review.id))
        .filter(models.Review.original_review_id.isnot(None))
        .group_by(models.Review.original_review_id)
        .all()
    )

    uid = current_user.id if current_user else None
    return [serialize_review(r, uid, repost_counts) for r in reviews]


@app.post("/api/reviews", response_model=schemas.ReviewResponse)
def create_review(
    payload: schemas.ReviewCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    review = models.Review(
        user_id=current_user.id,
        category=payload.category or "livro",
        work_title=payload.work_title.strip(),
        work_creator=(payload.work_creator or "").strip(),
        work_genre=(payload.work_genre or "").strip(),
        work_year=(payload.work_year or "").strip(),
        cover_url=(payload.cover_url or "").strip(),
        rating=payload.rating,
        status=payload.status or "concluido",
        title=(payload.title or "").strip(),
        content=(payload.content or "").strip(),
        has_spoiler=payload.has_spoiler,
        is_favorite=payload.is_favorite,
        finished_at=(payload.finished_at or "").strip(),
        skoob_book_id=payload.skoob_book_id,
        skoob_url=payload.skoob_url,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return serialize_review(review, current_user.id, {})


@app.put("/api/reviews/{review_id}", response_model=schemas.ReviewResponse)
def update_review(
    review_id: int,
    payload: schemas.ReviewUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    review = db.query(models.Review).filter(models.Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Resenha não encontrada.")
    if review.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Você só pode editar suas próprias resenhas.")

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        if isinstance(val, str):
            val = val.strip()
        setattr(review, field, val)

    db.commit()
    db.refresh(review)

    repost_count = (
        db.query(func.count(models.Review.id))
        .filter(models.Review.original_review_id == review.id)
        .scalar()
        or 0
    )
    return serialize_review(review, current_user.id, {review.id: repost_count})


@app.delete("/api/reviews/{review_id}")
def delete_review(
    review_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    review = db.query(models.Review).filter(models.Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Resenha não encontrada.")
    if review.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Você só pode apagar suas próprias resenhas.")

    db.delete(review)
    db.commit()
    return {"message": "Resenha excluída com sucesso."}


@app.post("/api/reviews/{review_id}/like")
def toggle_like(
    review_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    review = db.query(models.Review).filter(models.Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Resenha não encontrada.")

    existing = (
        db.query(models.ReviewLike)
        .filter(
            models.ReviewLike.review_id == review_id,
            models.ReviewLike.user_id == current_user.id,
        )
        .first()
    )
    if existing:
        db.delete(existing)
        liked = False
    else:
        db.add(models.ReviewLike(review_id=review_id, user_id=current_user.id))
        liked = True

    db.commit()
    total_likes = (
        db.query(func.count(models.ReviewLike.id))
        .filter(models.ReviewLike.review_id == review_id)
        .scalar()
        or 0
    )
    return {"liked": liked, "likes_count": total_likes}


@app.post("/api/reviews/{review_id}/repost", response_model=schemas.ReviewResponse)
def repost_review(
    review_id: int,
    payload: schemas.RepostCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target = db.query(models.Review).filter(models.Review.id == review_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Resenha original não encontrada.")

    # Se já for um repost, aponta para a resenha raiz
    root_review = target.original_review if target.original_review else target

    repost = models.Review(
        user_id=current_user.id,
        category=root_review.category,
        work_title=root_review.work_title,
        work_creator=root_review.work_creator,
        work_genre=root_review.work_genre,
        work_year=root_review.work_year,
        cover_url=root_review.cover_url,
        rating=root_review.rating,
        status=root_review.status,
        title=root_review.title,
        content=root_review.content,
        has_spoiler=root_review.has_spoiler,
        is_favorite=False,
        finished_at=root_review.finished_at,
        original_review_id=root_review.id,
        repost_comment=(payload.repost_comment or "").strip(),
    )
    db.add(repost)
    db.commit()
    db.refresh(repost)
    return serialize_review(repost, current_user.id, {})


@app.post("/api/reviews/{review_id}/comments", response_model=schemas.CommentResponse)
def add_comment(
    review_id: int,
    payload: schemas.CommentCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    review = db.query(models.Review).filter(models.Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Resenha não encontrada.")

    comment = models.Comment(
        review_id=review_id,
        user_id=current_user.id,
        content=payload.content.strip(),
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return schemas.CommentResponse.model_validate(comment)


@app.delete("/api/comments/{comment_id}")
def delete_comment(
    comment_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    comment = db.query(models.Comment).filter(models.Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comentário não encontrado.")
    if comment.user_id != current_user.id and comment.review.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para excluir este comentário.")

    db.delete(comment)
    db.commit()
    return {"message": "Comentário removido."}


# ==========================================
# Rotas de Importação do Skoob & Busca de Obras
# ==========================================
@app.post("/api/skoob/preview-url")
async def preview_skoob_url(
    payload: schemas.SkoobUrlImportRequest,
    current_user: models.User = Depends(get_current_user),
):
    try:
        items = await skoob_importer.fetch_skoob_from_url_or_id(
            payload.url_or_id, max_items=payload.max_items
        )
        if not items:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Não encontramos livros/resenhas públicas nesse link ou ID do Skoob. "
                    "Verifique se o perfil/estante está público ou use a aba de importação por arquivo (CSV/JSON/HTML)."
                ),
            )
        return {"count": len(items), "items": items}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Não foi possível acessar o Skoob diretamente ({str(e)}). Você também pode importar salvando a página HTML ou via CSV/JSON.",
        )


@app.post("/api/skoob/preview-file")
async def preview_skoob_file(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
):
    raw_bytes = await file.read()
    items = skoob_importer.parse_uploaded_file(file.filename or "skoob.csv", raw_bytes)
    if not items:
        raise HTTPException(
            status_code=400,
            detail="Nenhum livro ou avaliação pôde ser lido deste arquivo. Formatos aceitos: CSV, JSON ou HTML do Skoob.",
        )
    return {"count": len(items), "items": items}


@app.post("/api/skoob/import-batch")
def import_skoob_batch(
    items: List[schemas.ReviewCreate],
    skip_duplicates: bool = Query(default=True),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    imported = 0
    skipped = 0
    updated = 0

    for item in items:
        title_clean = item.work_title.strip()
        if not title_clean:
            continue

        existing = None
        if item.skoob_book_id:
            existing = (
                db.query(models.Review)
                .filter(
                    models.Review.user_id == current_user.id,
                    models.Review.skoob_book_id == item.skoob_book_id,
                )
                .first()
            )
        if not existing:
            existing = (
                db.query(models.Review)
                .filter(
                    models.Review.user_id == current_user.id,
                    func.lower(models.Review.work_title) == title_clean.lower(),
                    models.Review.original_review_id.is_(None),
                )
                .first()
            )

        if existing:
            if skip_duplicates:
                skipped += 1
                continue
            else:
                existing.rating = item.rating
                existing.status = item.status
                if item.content:
                    existing.content = item.content
                if item.cover_url:
                    existing.cover_url = item.cover_url
                if item.work_creator:
                    existing.work_creator = item.work_creator
                updated += 1
                continue

        new_rev = models.Review(
            user_id=current_user.id,
            category=item.category or "livro",
            work_title=title_clean,
            work_creator=(item.work_creator or "").strip(),
            work_genre=(item.work_genre or "").strip(),
            work_year=(item.work_year or "").strip(),
            cover_url=(item.cover_url or "").strip(),
            rating=item.rating,
            status=item.status or "concluido",
            title=(item.title or "").strip(),
            content=(item.content or "").strip(),
            has_spoiler=item.has_spoiler,
            is_favorite=item.is_favorite,
            finished_at=(item.finished_at or "").strip(),
            skoob_book_id=item.skoob_book_id,
            skoob_url=item.skoob_url,
        )
        db.add(new_rev)
        imported += 1

    db.commit()
    return {
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "message": f"{imported} avaliação(ões) importada(s) com sucesso!",
    }


@app.get("/api/media/search")
async def media_search(
    q: str = Query(..., min_length=2),
    category: str = Query(default="livro"),
):
    items = await skoob_importer.search_media_catalog(q, category)
    return {"items": items}


# ==========================================
# Servir Frontend (SPA em static/)
# ==========================================
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def serve_spa():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
