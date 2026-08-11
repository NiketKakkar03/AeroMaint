from typing import Any

from fastapi import APIRouter, Query
from packages.retrieval import Document, build_index

router = APIRouter(prefix="/documents", tags=["documents"])

_INDEX = build_index(
    [
        Document(
            source_url="https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC_43.13-1B_w-chg1.pdf",
            title="FAA AC 43.13-1B",
            version="Change 1",
            page=16,
            text=(
                "# Inspection principles\nMaintenance inspection evidence must be evaluated "
                "against approved data. Damage disposition and return-to-service decisions require "
                "appropriately authorized personnel."
            ),
        ),
        Document(
            source_url="https://ntrs.nasa.gov/citations/20090029214",
            title="NASA C-MAPSS turbofan degradation simulation",
            version="2008",
            page=1,
            text=(
                "# Prognostics dataset\nC-MAPSS simulates turbofan engine degradation "
                "trajectories for prognostics research. Remaining useful life labels describe "
                "simulated cycles and are not operational aircraft maintenance limits."
            ),
        ),
    ]
)


@router.get("/search")
async def search_documents(
    q: str = Query(min_length=2, max_length=500), limit: int = Query(5, ge=1, le=10)
) -> dict[str, Any]:
    result = _INDEX.search(q, limit=limit)
    return {
        "status": result.status,
        "query": result.query,
        "index_version": result.index_version,
        "results": list(result.results),
        "reason": result.reason,
    }
