"""FastAPI router for OTT / streaming discovery.

All availability data is sourced live from TMDB (powered by JustWatch) via the
shared server-side ``TMDBService`` — the TMDB API key never leaves the backend.
Nothing here fabricates provider availability: an empty region simply returns an
empty result set.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.core.constants import CONTENT_PAGE_SIZE
from app.services.tmdb.service import TMDBService

router = APIRouter(prefix="/ott", tags=["OTT"])

tmdb = TMDBService()

_VALID_TYPES = {"movie", "tv"}


def _validate_content_type(content_type: str) -> str:
    if content_type not in _VALID_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="content_type must be one of: movie, tv.",
        )
    return content_type


@router.get("/regions")
async def list_regions():
    """List ISO-3166-1 regions TMDB has streaming-provider data for."""
    data = await tmdb.watch_provider_regions()
    results = data.get("results") if isinstance(data, dict) else None
    regions = [
        {
            "iso_3166_1": r.get("iso_3166_1"),
            "english_name": r.get("english_name"),
            "native_name": r.get("native_name"),
        }
        for r in (results or [])
        if isinstance(r, dict) and r.get("iso_3166_1")
    ]
    regions.sort(key=lambda r: (r.get("english_name") or ""))
    return {"results": regions}


@router.get("/providers")
async def list_providers(
    region: str = Query(default="IN", min_length=2, max_length=2),
    content_type: str = Query(default="movie"),
):
    """List streaming providers available in ``region`` for the given media type.

    Providers are ordered by TMDB's region-specific display priority so the most
    prominent services in that country appear first.
    """
    ctype = _validate_content_type(content_type)
    region_code = region.upper()
    data = await tmdb.watch_providers_list(ctype, region_code)
    results = data.get("results") if isinstance(data, dict) else None

    def _priority(provider: dict) -> int:
        priorities = provider.get("display_priorities")
        if isinstance(priorities, dict) and region_code in priorities:
            return priorities[region_code]
        value = provider.get("display_priority")
        return value if isinstance(value, int) else 9999

    providers = [
        {
            "provider_id": p.get("provider_id"),
            "provider_name": p.get("provider_name"),
            "logo_path": p.get("logo_path"),
            "display_priority": _priority(p),
        }
        for p in (results or [])
        if isinstance(p, dict) and p.get("provider_id")
    ]
    providers.sort(key=lambda p: p["display_priority"])
    return {"region": region_code, "content_type": ctype, "results": providers}


@router.get("/{content_type}")
async def discover_by_provider(
    content_type: str,
    provider_id: int = Query(..., ge=1),
    region: str = Query(default="IN", min_length=2, max_length=2),
    page: int = Query(default=1, ge=1),
    sort_by: str = Query(default="popularity.desc"),
):
    """Discover titles available on a specific provider within a region.

    Returns one normalized content-grid page (see ``CONTENT_PAGE_SIZE``). An empty
    catalog for that provider/region is a valid outcome and yields an empty page
    rather than an error.
    """
    ctype = _validate_content_type(content_type)
    data = await tmdb.discover_by_provider(
        content_type=ctype,
        provider_id=provider_id,
        watch_region=region.upper(),
        page=page,
        sort_by=sort_by,
    )
    normalized = tmdb.normalize_page(data, page_size=CONTENT_PAGE_SIZE, raise_if_empty=False)
    # Stamp each result with its media type so the frontend renders the correct
    # card + detail route (TMDB discover payloads omit media_type).
    for item in normalized.get("results", []):
        if isinstance(item, dict):
            item.setdefault("content_type", ctype)
            item.setdefault("media_type", ctype)
    return normalized
