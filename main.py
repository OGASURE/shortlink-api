from datetime import datetime
import os
import string
import random

from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel, HttpUrl
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
)
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# -------------------------------------------------------------------
# Basic configuration
# -------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "shortlinks.db")

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Optional: for when you later put this behind a domain like links.workpent.com
BASE_SHORT_URL = os.getenv("BASE_SHORT_URL", "http://localhost:9500")

# -------------------------------------------------------------------
# Database model
# -------------------------------------------------------------------


class ShortLink(Base):
    __tablename__ = "shortlinks"

    id = Column(Integer, primary_key=True, index=True)
    short_code = Column(String(32), unique=True, index=True, nullable=False)
    target_url = Column(String(2048), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    click_count = Column(Integer, default=0, nullable=False)
    last_clicked_at = Column(DateTime, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    note = Column(String(255), nullable=True)  # optional label/description


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


# -------------------------------------------------------------------
# Pydantic schemas
# -------------------------------------------------------------------


class CreateLinkRequest(BaseModel):
    url: HttpUrl
    custom_code: str | None = None
    note: str | None = None


class ShortLinkResponse(BaseModel):
    short_code: str
    short_url: str
    target_url: str
    created_at: datetime
    click_count: int
    last_clicked_at: datetime | None
    active: bool
    note: str | None = None


class StatsResponse(BaseModel):
    short_code: str
    target_url: str
    created_at: datetime
    click_count: int
    last_clicked_at: datetime | None
    active: bool
    note: str | None = None


class ListLinksResponse(BaseModel):
    total: int
    items: list[ShortLinkResponse]


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def generate_short_code(length: int = 7) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(length))


def build_short_url(code: str) -> str:
    # BASE_SHORT_URL can be something like https://lnk.workpent.com later
    return f"{BASE_SHORT_URL.rstrip('/')}/{code}"


# -------------------------------------------------------------------
# FastAPI app
# -------------------------------------------------------------------

app = FastAPI(
    title="Workpent Shortlink API",
    description="Minimal commercial-ready link shortener API.",
    version="0.1.0",
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


# -------------------------------------------------------------------
# Public endpoints
# -------------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": "shortlink-api", "time": datetime.utcnow().isoformat()}


@app.post(
    "/links",
    response_model=ShortLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_link(payload: CreateLinkRequest, db: Session = Depends(get_db)):
    # Optional: enforce simple domain allowlist later.

    # If custom code requested, check it's free
    if payload.custom_code:
        existing = db.query(ShortLink).filter(
            ShortLink.short_code == payload.custom_code
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Custom code already in use.",
            )
        short_code = payload.custom_code
    else:
        # Auto-generate and ensure uniqueness
        for _ in range(10):
            short_code = generate_short_code()
            existing = (
                db.query(ShortLink)
                .filter(ShortLink.short_code == short_code)
                .first()
            )
            if not existing:
                break
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate unique short code.",
            )

    link = ShortLink(
        short_code=short_code,
        target_url=str(payload.url),
        note=payload.note,
    )
    db.add(link)
    db.commit()
    db.refresh(link)

    return ShortLinkResponse(
        short_code=link.short_code,
        short_url=build_short_url(link.short_code),
        target_url=link.target_url,
        created_at=link.created_at,
        click_count=link.click_count,
        last_clicked_at=link.last_clicked_at,
        active=link.active,
        note=link.note,
    )


@app.get("/{code}", response_class=RedirectResponse)
def redirect_link(code: str, request: Request, db: Session = Depends(get_db)):
    link = (
        db.query(ShortLink)
        .filter(ShortLink.short_code == code, ShortLink.active == True)  # noqa: E712
        .first()
    )
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found.")

    link.click_count += 1
    link.last_clicked_at = datetime.utcnow()
    db.commit()

    return RedirectResponse(url=link.target_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


# -------------------------------------------------------------------
# Simple stats + admin-style endpoints (no auth yet)
# -------------------------------------------------------------------


@app.get("/stats/{code}", response_model=StatsResponse)
def get_stats(code: str, db: Session = Depends(get_db)):
    link = db.query(ShortLink).filter(ShortLink.short_code == code).first()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found.")

    return StatsResponse(
        short_code=link.short_code,
        target_url=link.target_url,
        created_at=link.created_at,
        click_count=link.click_count,
        last_clicked_at=link.last_clicked_at,
        active=link.active,
        note=link.note,
    )


@app.get("/links", response_model=ListLinksResponse)
def list_links(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    q = db.query(ShortLink).order_by(ShortLink.created_at.desc())
    total = q.count()
    items_raw = q.offset(skip).limit(limit).all()

    items = [
        ShortLinkResponse(
            short_code=link.short_code,
            short_url=build_short_url(link.short_code),
            target_url=link.target_url,
            created_at=link.created_at,
            click_count=link.click_count,
            last_clicked_at=link.last_clicked_at,
            active=link.active,
            note=link.note,
        )
        for link in items_raw
    ]

    return ListLinksResponse(total=total, items=items)


@app.post("/links/{code}/deactivate", response_model=StatsResponse)
def deactivate_link(code: str, db: Session = Depends(get_db)):
    link = db.query(ShortLink).filter(ShortLink.short_code == code).first()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found.")
    link.active = False
    db.commit()
    db.refresh(link)

    return StatsResponse(
        short_code=link.short_code,
        target_url=link.target_url,
        created_at=link.created_at,
        click_count=link.click_count,
        last_clicked_at=link.last_clicked_at,
        active=link.active,
        note=link.note,
    )

