from typing import Annotated

from fastapi import APIRouter, Query, Request

from .geometry_read import batch
from .point_api import respond, service
from .public_points import PublicPointError
from .root_import import POINT

router = APIRouter()


@router.get("/api/v1/geometry")
def geometry(request: Request, ids: Annotated[str, Query(min_length=1, max_length=6207)]):
    def read():
        parts = ids.split(",")
        if any(not POINT.fullmatch(pid) for pid in parts):
            raise PublicPointError("INVALID_PARAMS", 400)
        return batch(service(request, {"ids"}), parts)

    return respond(read)
