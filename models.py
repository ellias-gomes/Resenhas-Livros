from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Float,
    Boolean,
    ForeignKey,
    DateTime,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from database import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    display_name = Column(String(100), nullable=False)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    bio = Column(Text, default="")
    avatar_emoji = Column(String(16), default="🌸")
    avatar_color = Column(String(20), default="#d8b4f8")
    avatar_url = Column(Text, nullable=True)
    skoob_id = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    reviews = relationship("Review", back_populates="author", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="author", cascade="all, delete-orphan")
    likes = relationship("ReviewLike", back_populates="user", cascade="all, delete-orphan")


class SessionToken(Base):
    __tablename__ = "session_tokens"

    token = Column(String(128), primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User")


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Categoria: 'livro', 'filme', 'serie'
    category = Column(String(30), nullable=False, default="livro", index=True)
    work_title = Column(String(255), nullable=False, index=True)
    work_creator = Column(String(200), nullable=False, default="")  # Autor(a) / Diretor(a)
    work_genre = Column(String(120), nullable=True, default="")
    work_year = Column(String(20), nullable=True, default="")
    cover_url = Column(Text, nullable=True, default="")

    # Avaliação e status
    rating = Column(Float, nullable=False, default=5.0)
    # Status: 'concluido', 'em_andamento', 'quero', 'abandonado'
    status = Column(String(30), nullable=False, default="concluido")
    title = Column(String(255), nullable=True, default="")
    content = Column(Text, nullable=False, default="")
    has_spoiler = Column(Boolean, default=False)
    is_favorite = Column(Boolean, default=False)
    finished_at = Column(String(30), nullable=True, default="")

    # Republicação / Compartilhamento dentro da rede social
    original_review_id = Column(Integer, ForeignKey("reviews.id", ondelete="SET NULL"), nullable=True)
    repost_comment = Column(Text, nullable=True, default="")

    # Rastreamento de importação do Skoob
    skoob_book_id = Column(String(100), nullable=True, index=True)
    skoob_url = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    author = relationship("User", back_populates="reviews")
    original_review = relationship("Review", remote_side=[id], uselist=False)
    likes = relationship("ReviewLike", back_populates="review", cascade="all, delete-orphan")
    comments = relationship(
        "Comment",
        back_populates="review",
        cascade="all, delete-orphan",
        order_by="Comment.created_at.asc()",
    )


class ReviewLike(Base):
    __tablename__ = "review_likes"
    __table_args__ = (UniqueConstraint("review_id", "user_id", name="uq_review_user_like"),)

    id = Column(Integer, primary_key=True, index=True)
    review_id = Column(Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    review = relationship("Review", back_populates="likes")
    user = relationship("User", back_populates="likes")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    review_id = Column(Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    review = relationship("Review", back_populates="comments")
    author = relationship("User", back_populates="comments")
