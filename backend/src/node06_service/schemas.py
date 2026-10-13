from pydantic import BaseModel, ConfigDict


class PublicSiteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    origin: str
    state: str
    display_name: str | None
    welcome_source: str
    settings_revision: int
    welcome_revision_id: str
    welcome_body: str
