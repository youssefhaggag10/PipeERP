from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.modules.identity.permissions import PermissionCode
from app.modules.identity.security import normalize_username, validate_password


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=512)


class UserView(BaseModel):
    id: UUID
    username: str
    display_name: str
    is_active: bool
    must_change_password: bool
    roles: list[str]
    permissions: list[PermissionCode]


class LoginResponse(BaseModel):
    user: UserView


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=12, max_length=512)

    @field_validator("new_password")
    @classmethod
    def valid_new_password(cls, value: str) -> str:
        validate_password(value)
        return value


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=12, max_length=512)
    role_codes: set[str] = Field(default_factory=set)
    must_change_password: bool = False

    @field_validator("username")
    @classmethod
    def valid_username(cls, value: str) -> str:
        normalize_username(value)
        return value.strip()

    @field_validator("password")
    @classmethod
    def valid_password(cls, value: str) -> str:
        validate_password(value)
        return value


class UpdateUserRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=160)
    is_active: bool | None = None
    role_codes: set[str] | None = None
    new_password: str | None = Field(default=None, min_length=12, max_length=512)
    must_change_password: bool | None = None

    @field_validator("new_password")
    @classmethod
    def valid_password(cls, value: str | None) -> str | None:
        if value is not None:
            validate_password(value)
        return value


class RoleView(BaseModel):
    id: UUID
    code: str
    name_ar: str
    description: str
    is_system: bool
    permissions: list[PermissionCode]


class CreateRoleRequest(BaseModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    name_ar: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=1000)
    permissions: set[PermissionCode] = Field(default_factory=set)


class UpdateRolePermissionsRequest(BaseModel):
    permissions: set[PermissionCode]


class AuditLogView(BaseModel):
    id: UUID
    actor_user_id: UUID | None
    event_type: str
    entity_type: str
    entity_id: str | None
    outcome: str
    details: dict[str, object] | None
    created_at: datetime


class MessageResponse(BaseModel):
    message: str
