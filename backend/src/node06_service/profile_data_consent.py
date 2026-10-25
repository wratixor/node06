"""Explicit data-consent extension. V1 control-only invitations remain unchanged."""

from typing import Literal

from pydantic import Field, model_validator

from .profile_links import Metadata, Peer, Secret, Token
from .profile_preferences import Scopes


class Create(Peer):
    send: Scopes = Field(default_factory=list)
    receive: Scopes = Field(default_factory=list)

    @model_validator(mode="after")
    def canonical_scopes(self):
        if len(set(self.send)) != len(self.send) or len(set(self.receive)) != len(self.receive):
            raise ValueError("Duplicate scope")
        self.send.sort()
        self.receive.sort()
        return self


class DataMetadata(Metadata):
    protocol: Literal["node06-profile-sync/1"] = "node06-profile-sync/1"
    send: Scopes
    receive: Scopes


class DataToken(Token):
    protocol: Literal["node06-profile-sync/1"]
    data_token: Secret
    send: Scopes
    receive: Scopes
