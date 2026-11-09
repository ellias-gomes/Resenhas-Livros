from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class UserRegister(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    display_name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., min_length=4, max_length=120)
    password: str = Field(..., min_length=4, max_length=100)
    bio: Optional[str] = ""
    avatar_emoji: Optional[str] = "🌸"
    avatar_color: Optional[str] = "#d8b4f8"


class UserLogin(BaseModel):
    login: str  # username ou email
    password: str


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_emoji: Optional[str] = None
    avatar_color: Optional[str] = None
    avatar_url: Optional[str] = None
    skoob_id: Optional[str] = None


class UserBrief(BaseModel):
    id: int
    username: str
    display_name: str
    bio: Optional[str] = ""
    avatar_emoji: Optional[str] = "🌸"
    avatar_color: Optional[str] = "#d8b4f8"
    avatar_url: Optional[str] = None
    skoob_id: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AuthResponse(BaseModel):
    token: str
    user: UserBrief


class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class CommentResponse(BaseModel):
    id: int
    review_id: int
    user_id: int
    content: str
    created_at: datetime
    author: UserBrief

    class Config:
        from_attributes = True


class ReviewCreate(BaseModel):
    category: str = "livro"  # 'livro', 'filme', 'serie'
    work_title: str = Field(..., min_length=1, max_length=255)
    work_creator: Optional[str] = ""
    work_genre: Optional[str] = ""
    work_year: Optional[str] = ""
    cover_url: Optional[str] = ""
    rating: float = Field(5.0, ge=0.0, le=5.0)
    status: str = "concluido"  # 'concluido', 'em_andamento', 'quero', 'abandonado'
    title: Optional[str] = ""
    content: str = ""
    has_spoiler: bool = False
    is_favorite: bool = False
    finished_at: Optional[str] = ""
    skoob_book_id: Optional[str] = None
    skoob_url: Optional[str] = None


class ReviewUpdate(BaseModel):
    category: Optional[str] = None
    work_title: Optional[str] = None
    work_creator: Optional[str] = None
    work_genre: Optional[str] = None
    work_year: Optional[str] = None
    cover_url: Optional[str] = None
    rating: Optional[float] = Field(None, ge=0.0, le=5.0)
    status: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    has_spoiler: Optional[bool] = None
    is_favorite: Optional[bool] = None
    finished_at: Optional[str] = None


class RepostCreate(BaseModel):
    repost_comment: Optional[str] = ""


class OriginalReviewSnippet(BaseModel):
    id: int
    category: str
    work_title: str
    work_creator: Optional[str] = ""
    work_genre: Optional[str] = ""
    work_year: Optional[str] = ""
    cover_url: Optional[str] = ""
    rating: float
    status: str
    title: Optional[str] = ""
    content: str
    has_spoiler: bool
    is_favorite: bool
    finished_at: Optional[str] = ""
    skoob_url: Optional[str] = None
    created_at: datetime
    author: UserBrief

    class Config:
        from_attributes = True


class ReviewResponse(BaseModel):
    id: int
    user_id: int
    category: str
    work_title: str
    work_creator: Optional[str] = ""
    work_genre: Optional[str] = ""
    work_year: Optional[str] = ""
    cover_url: Optional[str] = ""
    rating: float
    status: str
    title: Optional[str] = ""
    content: str
    has_spoiler: bool
    is_favorite: bool
    finished_at: Optional[str] = ""
    original_review_id: Optional[int] = None
    repost_comment: Optional[str] = ""
    skoob_book_id: Optional[str] = None
    skoob_url: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    author: UserBrief
    original_review: Optional[OriginalReviewSnippet] = None
    likes_count: int = 0
    liked_by_me: bool = False
    reposts_count: int = 0
    comments_count: int = 0
    comments: List[CommentResponse] = []

    class Config:
        from_attributes = True


class SkoobUrlImportRequest(BaseModel):
    url_or_id: str
    import_mode: str = "auto"  # 'auto', 'single', 'shelf'
    max_items: int = Field(100, ge=1, le=500)
