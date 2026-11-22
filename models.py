"""Модели предметной области (простые структуры данных)."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class User:
    id: int
    username: str
    email: str
    role: str
    created_at: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


@dataclass
class Title:
    id: int
    name: str
    original_name: str
    kind: str
    year: int
    country: str
    episodes: int
    duration: int
    description: str
    alt_names: str = ""
    genres: list[str] = field(default_factory=list)
    poster: str = ""
    avg_score: Optional[float] = None
    votes: int = 0


@dataclass
class ListEntry:
    id: int
    user_id: int
    title_id: int
    title_name: str
    kind: str
    status: str
    score: Optional[int]
    progress: int
    episodes: int
    duration: int
    updated_at: str


@dataclass
class Review:
    id: int
    user_id: int
    username: str
    title_id: int
    text: str
    created_at: str


@dataclass
class SearchFilters:
    query: str = ""
    kind: Optional[str] = None
    genre: Optional[str] = None
    country: Optional[str] = None
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    min_score: Optional[float] = None
    sort: str = "rating"


@dataclass
class UserStats:
    counts: dict[str, int]
    total: int
    mean_score: Optional[float]
    minutes_watched: int
    top_genre: Optional[str]
