from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class DriftPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False, strict=True)
    property_name: str = Field(min_length=1, max_length=128)
    minimum_samples: int = Field(default=100, ge=20)
    bins: int = Field(default=10, ge=2, le=100)
    psi_limit: float = Field(default=0.2, gt=0)
    ks_limit: float = Field(default=0.2, gt=0, le=1)
    maximum_missing_fraction: float = Field(default=0.05, ge=0, lt=1)


class DriftReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False, strict=True)
    property_name: str
    status: Literal["healthy", "drift", "invalid"]
    reference_count: int = Field(ge=0)
    observed_count: int = Field(ge=0)
    psi: float | None = Field(default=None, ge=0)
    ks_statistic: float | None = Field(default=None, ge=0, le=1)
    reason: str


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    action_type: str = Field(min_length=1, max_length=128)
    object_id: str = Field(min_length=1, max_length=256)
    expected_revision: int = Field(ge=0)
