from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import engine
from app.api.routes.places import router as places_router
from app.api.routes.assistant import router as assistant_router


app = FastAPI(
    title="CityBuddy API",
    version="0.1.0",
    description="Location-aware recommendations for places and experiences.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://jolly-ocean-08e208710.7.azurestaticapps.net",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(places_router)
app.include_router(assistant_router)


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "application": "CityBuddy API",
        "version": "0.1.0",
    }


@app.get("/api/health/database")
def database_health_check():
    try:
        with engine.connect() as connection:
            result = connection.execute(
                text(
                    """
                    SELECT
                        current_database() AS database,
                        PostGIS_Version() AS postgis_version
                    """
                )
            ).mappings().one()

        return {
            "status": "healthy",
            "database": result["database"],
            "postgis_version": result["postgis_version"],
        }

    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=503,
            detail="Database connection is unavailable.",
        ) from error
