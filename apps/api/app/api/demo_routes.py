from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import ConfigDict
from pydantic.alias_generators import to_camel

from ..core.http import APIError
from ..demo.seed import DEMO_CANDIDATE_USER_ID, DEMO_EMPLOYER_USER_ID, ensure_demo_world
from ..persistence.store import NotFoundError
from .contracts import ERROR_RESPONSES
from .routes import (
    RequestModel,
    ResponseModel,
    UserResponse,
    auth_service,
    require_sqlalchemy_store,
)

router = APIRouter(responses=ERROR_RESPONSES)

DEMO_USERS_BY_ACT = {
    "employer": DEMO_EMPLOYER_USER_ID,
    "candidate": DEMO_CANDIDATE_USER_ID,
}


class DemoSessionRequest(RequestModel):
    model_config = ConfigDict(extra="forbid", alias_generator=to_camel, populate_by_name=True)

    act: str


class DemoSessionResponse(ResponseModel):
    user: UserResponse
    token: str
    token_type: str = "Bearer"
    expires_at: datetime


@router.post("/api/demo/session", response_model=DemoSessionResponse)
async def create_demo_session(
    input_data: DemoSessionRequest, request: Request
) -> DemoSessionResponse:
    user_id = DEMO_USERS_BY_ACT.get(input_data.act)
    if user_id is None:
        raise APIError(400, "INVALID_REQUEST", "Unknown demo act")
    store = require_sqlalchemy_store(request)
    await ensure_demo_world(store, request.app.state.settings)
    try:
        user = await store.user(user_id)
    except NotFoundError:
        raise APIError(503, "SERVICE_UNAVAILABLE", "Demo workspace is unavailable") from None
    result = auth_service(request).issue_token(user)
    return DemoSessionResponse(
        user=UserResponse.model_validate(result.user),
        token=result.token,
        expires_at=result.expires_at,
    )
