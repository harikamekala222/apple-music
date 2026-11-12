from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

import boto3
from botocore.config import Config

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError

from app.settings import (
    R2_ENDPOINT,
    R2_ACCESS_KEY,
    R2_SECRET_KEY,
    R2_BUCKET,
    DATABASE_URL
)


# ==========================================
# CONFIGURATION
# ==========================================

FALLBACK_ARTWORK = (
    "https://images.unsplash.com/"
    "photo-1614613535308-eb5fbd3d2c17"
)

# Check whether actual R2 credentials exist.
# Empty values and example placeholders are ignored.

def valid_setting(value):
    if not value:
        return False

    value = str(value).strip()

    if not value:
        return False

    if "YOUR_" in value.upper():
        return False

    return True


# ==========================================
# OPTIONAL CLOUDFLARE R2 CONFIGURATION
# ==========================================

s3_client = None

r2_configured = all([
    valid_setting(R2_ENDPOINT),
    valid_setting(R2_ACCESS_KEY),
    valid_setting(R2_SECRET_KEY),
    valid_setting(R2_BUCKET)
])

if r2_configured:
    try:
        s3_client = boto3.client(
            "s3",
            endpoint_url=R2_ENDPOINT,
            aws_access_key_id=R2_ACCESS_KEY,
            aws_secret_access_key=R2_SECRET_KEY,
            config=Config(signature_version="s3v4")
        )

        print("Cloudflare R2 configured successfully")

    except Exception as e:
        print(f"R2 disabled: {e}")
        s3_client = None

else:
    print(
        "Cloudflare R2 is disabled. "
        "Running without external music storage."
    )


# ==========================================
# DATABASE CONFIGURATION
# ==========================================

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

TRACKS_READY = False


def get_db():
    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()


# ==========================================
# FASTAPI INITIALIZATION
# ==========================================

app = FastAPI(
    title="Music App Backend",
    description="Apple Music Application API",
    version="1.0.0"
)


origins = [
    "https://music.kyawhtet.com",
    "https://www.music.kyawhtet.com",
    "https://music-app-nine-dun.vercel.app",
    "https://apple-music-522y.onrender.com",
    "http://localhost:5173",
    "http://localhost:3000"
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ==========================================
# DATABASE TABLE INITIALIZATION
# ==========================================

def initialize_tracks_table(db: Session):

    is_postgres = engine.dialect.name == "postgresql"

    id_column = (
        "SERIAL PRIMARY KEY"
        if is_postgres
        else "INTEGER PRIMARY KEY AUTOINCREMENT"
    )

    db.execute(
        text(f"""
            CREATE TABLE IF NOT EXISTS tracks (
                track_id {id_column},
                album_name TEXT,
                track_name TEXT,
                audio_key TEXT UNIQUE,
                cover_key TEXT
            )
        """)
    )

    db.commit()


# ==========================================
# OPTIONAL R2 TRACK SYNCHRONIZATION
# ==========================================

def sync_tracks_from_r2(db: Session):

    if s3_client is None:
        return

    response = s3_client.list_objects_v2(
        Bucket=R2_BUCKET
    )

    album_files = {}

    for obj in response.get("Contents", []):

        key = obj["Key"]

        parts = key.split("/")

        if len(parts) <= 1:
            continue

        album_name = parts[0]

        if album_name not in album_files:

            album_files[album_name] = {
                "tracks": [],
                "images": []
            }

        lower_key = key.lower()

        if lower_key.endswith(".mp3"):

            album_files[album_name]["tracks"].append(key)

        elif lower_key.endswith(
            (".jpg", ".jpeg", ".png", ".webp")
        ):

            album_files[album_name]["images"].append(key)

    initialize_tracks_table(db)

    for album_name, files in album_files.items():

        cover_key = None

        for image_key in files["images"]:

            lower_image = image_key.lower()

            if any(
                token in lower_image
                for token in [
                    "cover",
                    "front",
                    "folder",
                    "thumb",
                    "tape"
                ]
            ):

                cover_key = image_key
                break

        if cover_key is None and files["images"]:
            cover_key = files["images"][0]

        for audio_key in files["tracks"]:

            track_name = (
                audio_key.rsplit("/", 1)[-1]
                .rsplit(".", 1)[0]
            )

            db.execute(
                text("""
                    INSERT INTO tracks (
                        album_name,
                        track_name,
                        audio_key,
                        cover_key
                    )
                    VALUES (
                        :album_name,
                        :track_name,
                        :audio_key,
                        :cover_key
                    )
                    ON CONFLICT (audio_key) DO NOTHING
                """),
                {
                    "album_name": album_name,
                    "track_name": track_name,
                    "audio_key": audio_key,
                    "cover_key": cover_key
                }
            )

    db.commit()


# ==========================================
# ENSURE TRACKS TABLE IS READY
# ==========================================

def ensure_tracks_ready(db: Session):

    global TRACKS_READY

    if TRACKS_READY:
        return

    # Always create the table safely.
    # Existing records are preserved.

    initialize_tracks_table(db)

    # Run without R2.
    if s3_client is None:

        TRACKS_READY = True

        print(
            "Running without R2. "
            "Tracks table initialized."
        )

        return

    try:

        result = db.execute(
            text("SELECT COUNT(*) FROM tracks")
        ).scalar()

        if result and result > 0:

            TRACKS_READY = True
            return

        sync_tracks_from_r2(db)

        TRACKS_READY = True

        print("Track synchronization completed.")

    except Exception as e:

        db.rollback()

        print(f"R2 synchronization skipped: {e}")

        TRACKS_READY = True


# ==========================================
# FETCH TRACKS
# ==========================================

def fetch_tracks(db: Session):

    ensure_tracks_ready(db)

    result = db.execute(
        text("""
            SELECT
                track_id,
                album_name,
                track_name,
                audio_key,
                cover_key
            FROM tracks
            ORDER BY track_id ASC
        """)
    )

    return [
        dict(row._mapping)
        for row in result
    ]


# ==========================================
# BUILD ALBUM RESPONSE
# ==========================================

def build_albums(tracks):

    albums = {}

    for track in tracks:

        album_name = track["album_name"]

        if album_name not in albums:

            cover_url = (
                f"/artwork/{track['track_id']}"
                if track.get("cover_key")
                else FALLBACK_ARTWORK
            )

            albums[album_name] = {
                "id": len(albums) + 1,
                "name": album_name,
                "tracks": [],
                "cover": cover_url
            }

        albums[album_name]["tracks"].append({
            "track_id": track["track_id"],
            "name": track["track_name"]
        })

    return list(albums.values())


# ==========================================
# HEALTH CHECK
# ==========================================

@app.get("/health")
def health_check():

    return {
        "status": "healthy",
        "database": "configured",
        "storage": (
            "enabled"
            if s3_client is not None
            else "disabled"
        )
    }


# ==========================================
# ARTWORK ENDPOINT
# ==========================================

@app.get("/artwork/{track_id}")
def get_artwork(
    track_id: int,
    db: Session = Depends(get_db)
):

    if s3_client is None:

        return RedirectResponse(
            FALLBACK_ARTWORK
        )

    result = db.execute(
        text("""
            SELECT cover_key
            FROM tracks
            WHERE track_id = :tid
        """),
        {"tid": track_id}
    ).fetchone()

    if not result or not result[0]:

        return RedirectResponse(
            FALLBACK_ARTWORK
        )

    cover_key = result[0]

    try:

        url = s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": R2_BUCKET,
                "Key": cover_key
            },
            ExpiresIn=3600
        )

        return RedirectResponse(url)

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Artwork error: {str(e)}"
        )


# ==========================================
# ALBUM ENDPOINT
# ==========================================

@app.get("/albums")
def albums_only(
    db: Session = Depends(get_db)
):

    tracks = fetch_tracks(db)

    albums = build_albums(tracks)

    return [
        {
            "id": album["id"],
            "name": album["name"]
        }
        for album in albums
    ]


# ==========================================
# ALBUMS WITH TRACKS ENDPOINT
# ==========================================

@app.get("/albums-with-tracks")
def albums_with_tracks(
    db: Session = Depends(get_db)
):

    tracks = fetch_tracks(db)

    albums = build_albums(tracks)

    return albums


# ==========================================
# MUSIC STREAMING ENDPOINT
# ==========================================

@app.get("/stream/{track_id}")
def stream(
    track_id: int,
    db: Session = Depends(get_db)
):

    if s3_client is None:

        raise HTTPException(
            status_code=503,
            detail="Music storage is currently disabled."
        )

    result = db.execute(
        text("""
            SELECT audio_key
            FROM tracks
            WHERE track_id = :tid
        """),
        {"tid": track_id}
    ).fetchone()

    if not result:

        raise HTTPException(
            status_code=404,
            detail="Track not found"
        )

    audio_key = result[0]

    try:

        url = s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": R2_BUCKET,
                "Key": audio_key
            },
            ExpiresIn=3600
        )

        return RedirectResponse(url)

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Error generating stream URL: {str(e)}"
        )


# ==========================================
# APPLICATION STARTUP
# ==========================================

@app.on_event("startup")
def startup_event():

    print("Apple Music Backend Started")

    if s3_client is None:

        print("External music storage: DISABLED")

    else:

        print("External music storage: ENABLED")


# ==========================================
# RUN APPLICATION
# ==========================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000
    )
