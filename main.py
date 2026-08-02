import os
import sys
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from fastapi.responses import Response

from calculator import calculate_natal_chart, calculate_synastry, calculate_transits, _make_subject
from city_repository import CityRepositoryError
from geocoder import get_coordinates, search_cities

load_dotenv()

# ── Startup: validate SERVICE_SECRET ──────────────────────────────────────────
# Read once at startup; never re-read per-request to avoid env mutation races.
_SERVICE_SECRET: str = os.getenv("SERVICE_SECRET", "")
_ENVIRONMENT: str = os.getenv("ENVIRONMENT", "production")

if not _SERVICE_SECRET and _ENVIRONMENT != "development":
    print(
        "FATAL: SERVICE_SECRET is not set. "
        "Set ENVIRONMENT=development to disable this check locally.",
        file=sys.stderr,
    )
    sys.exit(1)

app = FastAPI(title="Astro Service")


# ── Auth ──────────────────────────────────────────────────────────────────────

def _check_secret(x_service_secret: Optional[str] = Header(None, alias="X-Service-Secret")):
    if _SERVICE_SECRET and x_service_secret != _SERVICE_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ── Request models ────────────────────────────────────────────────────────────

class NatalRequest(BaseModel):
    name: str
    birth_date: str          # YYYY-MM-DD
    birth_time: str          # HH:MM
    birth_city: Optional[str] = None
    birth_lat: Optional[float] = None
    birth_lng: Optional[float] = None
    timezone: Optional[str] = None


class TransitRequest(BaseModel):
    birth_date: str          # YYYY-MM-DD
    birth_time: str          # HH:MM
    birth_lat: float
    birth_lng: float
    timezone: str
    target_date: str         # YYYY-MM-DD


class PersonData(BaseModel):
    name: Optional[str] = None
    birth_date: str
    birth_time: str
    birth_lat: float
    birth_lng: float
    timezone: str


class SynastryRequest(BaseModel):
    person1: PersonData
    person2: PersonData


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/geocode/search", dependencies=[Depends(_check_secret)])
def geocode_search(q: str, limit: int = 6):
    if len(q) < 2:
        return []
    try:
        return search_cities(q, limit=min(limit, 10))
    except CityRepositoryError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Geocode error: {e}")


@app.post("/calculate", dependencies=[Depends(_check_secret)])
def calculate(req: NatalRequest):
    lat, lng, tz = req.birth_lat, req.birth_lng, req.timezone

    if lat is None or lng is None:
        if not req.birth_city:
            raise HTTPException(
                status_code=422,
                detail="Provide birth_lat/birth_lng or birth_city",
            )
        try:
            geo = get_coordinates(req.birth_city)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        lat, lng = geo["lat"], geo["lng"]
        if tz is None:
            tz = geo["timezone"]

    if tz is None:
        raise HTTPException(status_code=422, detail="timezone is required")

    year, month, day = (int(p) for p in req.birth_date.split("-"))
    hour, minute = (int(p) for p in req.birth_time.split(":"))

    return calculate_natal_chart(
        req.name, year, month, day, hour, minute,
        lat, lng, tz, req.birth_city or "",
    )


_SVG_STYLE = """<style>
  svg { background: #f0e9d8; }
  text { font-family: 'IBM Plex Mono', monospace; fill: #1f1d1a; }
  circle, line, path { stroke: #1f1d1a; }
  [fill="white"], [fill="#ffffff"] { fill: #f0e9d8; }
  [fill="black"], [fill="#000000"] { fill: #1f1d1a; }
</style>"""


@app.post("/natal/svg", dependencies=[Depends(_check_secret)])
def natal_svg(req: NatalRequest):
    lat, lng, tz = req.birth_lat, req.birth_lng, req.timezone

    if lat is None or lng is None:
        if not req.birth_city:
            raise HTTPException(status_code=422, detail="Provide birth_lat/birth_lng or birth_city")
        try:
            geo = get_coordinates(req.birth_city)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Geocode error: {e}")
        lat, lng = geo["lat"], geo["lng"]
        if tz is None:
            tz = geo["timezone"]

    if tz is None:
        raise HTTPException(status_code=422, detail="timezone is required")

    year, month, day = (int(p) for p in req.birth_date.split("-"))
    hour, minute = (int(p) for p in req.birth_time.split(":"))

    subject = _make_subject(req.name, year, month, day, hour, minute, lat, lng, tz, req.birth_city or "")

    try:
        from kerykeion import ChartDataFactory
        from kerykeion.charts.chart_drawer import ChartDrawer
        chart_data = ChartDataFactory.create_chart_data("Natal", subject)
        drawer = ChartDrawer(chart_data)
        svg_string = drawer.generate_wheel_only_svg_string()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"SVG generation failed: {e}")

    import re
    svg_string = re.sub(r'(<svg\b[^>]*>)', r'\1' + _SVG_STYLE, svg_string, count=1)

    return Response(content=svg_string, media_type="image/svg+xml")


@app.post("/transits", dependencies=[Depends(_check_secret)])
def transits(req: TransitRequest):
    year, month, day = (int(p) for p in req.birth_date.split("-"))
    hour, minute = (int(p) for p in req.birth_time.split(":"))

    return calculate_transits(
        year, month, day, hour, minute,
        req.birth_lat, req.birth_lng, req.timezone,
        req.target_date,
    )


@app.post("/synastry", dependencies=[Depends(_check_secret)])
def synastry(req: SynastryRequest):
    def _as_dict(p: PersonData) -> dict:
        return {
            "name": p.name,
            "birth_date": p.birth_date,
            "birth_time": p.birth_time,
            "birth_lat": p.birth_lat,
            "birth_lng": p.birth_lng,
            "timezone": p.timezone,
        }

    return calculate_synastry(_as_dict(req.person1), _as_dict(req.person2))
