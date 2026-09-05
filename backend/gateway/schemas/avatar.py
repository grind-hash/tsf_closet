"""3D モデル(VRM)登録の API モデル。"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from ..services.avatar_service import AVATAR_NAME_MAX_LEN


class AvatarUpdateRequest(BaseModel):
    """None の項目は据え置き。character_name / variant_label は空文字で解除。"""

    name: str | None = Field(default=None, min_length=1, max_length=AVATAR_NAME_MAX_LEN)
    character_name: str | None = Field(default=None, max_length=AVATAR_NAME_MAX_LEN)
    variant_label: str | None = Field(default=None, max_length=AVATAR_NAME_MAX_LEN)

    @model_validator(mode="after")
    def require_any_field(self) -> AvatarUpdateRequest:
        if (
            self.name is None
            and self.character_name is None
            and self.variant_label is None
        ):
            raise ValueError("no fields to update")
        return self
