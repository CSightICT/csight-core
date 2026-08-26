"""Immutable, code-based prompt manifests and registry contracts."""

import hashlib
import json
from collections.abc import Mapping
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


def canonical_prompt_hash(
    *,
    name: str,
    version: str,
    input_schema_version: str,
    output_schema_version: str,
    system_template: str,
    user_template: str,
) -> str:
    """Hash a canonical JSON representation of every behavior-bearing field."""

    encoded = json.dumps(
        {
            "input_schema_version": input_schema_version,
            "name": name,
            "output_schema_version": output_schema_version,
            "system_template": system_template,
            "user_template": user_template,
            "version": version,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class PromptManifest(BaseModel):
    """A versioned prompt snapshot whose hash detects silent in-place changes."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=32)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_schema_version: str = Field(min_length=1, max_length=32)
    output_schema_version: str = Field(min_length=1, max_length=32)
    system_template: str = Field(min_length=1, max_length=20_000, repr=False)
    user_template: str = Field(min_length=1, max_length=20_000, repr=False)

    @classmethod
    def create(
        cls,
        *,
        name: str,
        version: str,
        input_schema_version: str,
        output_schema_version: str,
        system_template: str,
        user_template: str,
    ) -> Self:
        name = name.strip()
        version = version.strip()
        input_schema_version = input_schema_version.strip()
        output_schema_version = output_schema_version.strip()
        system_template = system_template.strip()
        user_template = user_template.strip()
        content_hash = canonical_prompt_hash(
            name=name,
            version=version,
            input_schema_version=input_schema_version,
            output_schema_version=output_schema_version,
            system_template=system_template,
            user_template=user_template,
        )
        return cls(
            name=name,
            version=version,
            content_hash=content_hash,
            input_schema_version=input_schema_version,
            output_schema_version=output_schema_version,
            system_template=system_template,
            user_template=user_template,
        )

    @model_validator(mode="after")
    def verify_content_hash(self) -> Self:
        expected = canonical_prompt_hash(
            name=self.name,
            version=self.version,
            input_schema_version=self.input_schema_version,
            output_schema_version=self.output_schema_version,
            system_template=self.system_template,
            user_template=self.user_template,
        )
        if self.content_hash != expected:
            raise ValueError("content_hash does not match the canonical prompt manifest")
        return self

    def render_user(self, input_data: Mapping[str, object]) -> str:
        """Embed untrusted input as escaped JSON in the manifest's sole placeholder."""

        if self.user_template.count("{input_json}") != 1:
            raise ValueError("user_template must contain exactly one {input_json} placeholder")
        input_json = json.dumps(
            dict(input_data),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return self.user_template.replace("{input_json}", input_json)


class PromptRegistry:
    """Immutable lookup table keyed by prompt name and version."""

    def __init__(self, manifests: tuple[PromptManifest, ...]) -> None:
        entries = {(manifest.name, manifest.version): manifest for manifest in manifests}
        if len(entries) != len(manifests):
            raise ValueError("prompt registry contains a duplicate name/version")
        self._entries = entries

    def get(self, *, name: str, version: str) -> PromptManifest:
        try:
            return self._entries[(name, version)]
        except KeyError as error:
            raise KeyError(f"unknown prompt manifest: {name}:{version}") from error
