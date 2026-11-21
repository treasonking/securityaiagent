"""Declarative synthetic API contracts: no expressions, scripts, or URL evaluation."""
from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Name = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")]
Selector = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*){0,5}$", max_length=160)]
DocumentId = re.compile(r"doc-[a-z]+-[0-9]{3}")


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, validate_default=True)


class HttpRoutes(FrozenModel):
    login_path: str = "/login"
    list_path: str = "/documents"
    detail_path: str = "/documents/{document_id}"

    @model_validator(mode="after")
    def safe_paths(self):
        for value in (self.login_path, self.list_path, self.detail_path):
            if not re.fullmatch(r"/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+(?:/\{document_id\})?", value):
                raise ValueError("only canonical literal paths and a final document_id segment are supported")
            if len(value) > 200:
                raise ValueError("path is too long")
        if "{" in self.login_path or "{" in self.list_path or not self.detail_path.endswith("/{document_id}"):
            raise ValueError("document_id is required only in the detail template")
        if self.login_path == self.list_path:
            raise ValueError("login and list routes must differ")
        return self

    def detail(self, document_id: str) -> str:
        if not isinstance(document_id, str) or not DocumentId.fullmatch(document_id):
            raise ValueError("invalid synthetic document ID")
        return self.detail_path.replace("{document_id}", document_id)


class CredentialRef(FrozenModel):
    username: Name
    password_env: Literal["LAB_USER_A_PASSWORD", "LAB_USER_B_PASSWORD", "LAB_ADMIN_PASSWORD"]


class AccountRefs(FrozenModel):
    user_a: CredentialRef = CredentialRef(username="user_a", password_env="LAB_USER_A_PASSWORD")
    user_b: CredentialRef = CredentialRef(username="user_b", password_env="LAB_USER_B_PASSWORD")
    admin: CredentialRef = CredentialRef(username="admin", password_env="LAB_ADMIN_PASSWORD")

    @model_validator(mode="after")
    def distinct_accounts(self):
        refs = (self.user_a, self.user_b, self.admin)
        if len({ref.username for ref in refs}) != 3 or len({ref.password_env for ref in refs}) != 3:
            raise ValueError("account references must be distinct")
        return self


class ApiAdapter(FrozenModel):
    adapter_id: Name = "synthetic-documents"
    routes: HttpRoutes = HttpRoutes()
    accounts: AccountRefs = AccountRefs()
    login_user_field: Name = "username"
    login_password_field: Name = "password"
    auth_mode: Literal["cookie", "bearer"] = "cookie"
    cookie_name: Name | None = "lab_session"
    token_field: Selector | None = None
    identity_header: Name = "X-SecurityLab-Account"
    list_field: Selector = "documents"
    list_account_field: Selector = "account_id"
    list_id_field: Selector = "document_id"
    list_owner_field: Selector = "owner_id"
    resource_id_field: Selector = "document_id"
    owner_field: Selector = "owner_id"
    visibility_field: Selector = "visibility"
    private_value: str | bool = "private"
    public_value: str | bool = "public"
    content_field: Selector = "canary.value"
    content_kind_field: Selector = "canary.kind"
    content_kind_value: Name = "synthetic-private"
    content_container_field: Selector = "canary"
    legacy_marker_field: Selector = "marker"
    denial_field: Selector = "detail"
    denial_value: str = Field(default="document not found", min_length=1, max_length=80)

    @model_validator(mode="after")
    def auth_contract(self):
        if self.login_user_field == self.login_password_field:
            raise ValueError("login fields must differ")
        if self.auth_mode == "cookie" and (self.cookie_name is None or self.token_field is not None):
            raise ValueError("cookie mode requires only cookie_name")
        if self.auth_mode == "bearer" and (self.token_field is None or self.cookie_name is not None):
            raise ValueError("bearer mode requires only token_field")
        if type(self.private_value) is type(self.public_value) and self.private_value == self.public_value:
            raise ValueError("private and public values must differ")
        return self

    def login_payload(self, credentials):
        return {self.login_user_field: credentials[0], self.login_password_field: credentials[1]}


def select(payload, selector: str):
    """Bounded object-key lookup, never eval, JSONPath, array traversal, or interpolation."""
    for key in selector.split("."):
        if not isinstance(payload, dict) or key not in payload:
            return None
        payload = payload[key]
    return payload
