from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, field_validator, model_validator

from src.api.dependencies import DbSession
from src.credits.config_service import ConfigService

router = APIRouter(prefix="/api/v1", tags=["credit-config"])


class CreditConfigRequest(BaseModel):
    default_initial_balance: int
    activity_earning_rules: dict[str, int]
    service_costs: dict[str, int]
    streak_bonus_7d: int
    streak_bonus_30d: int
    tier_thresholds: dict[str, int]
    tier_multipliers: dict[str, float]
    tier_discounts: dict[str, float]

    @field_validator("service_costs")
    @classmethod
    def service_costs_positive(cls, v: dict[str, int]) -> dict[str, int]:
        if any(cost < 1 for cost in v.values()):
            raise ValueError("All service costs must be >= 1")
        return v

    @field_validator("activity_earning_rules")
    @classmethod
    def earning_rules_non_negative(cls, v: dict[str, int]) -> dict[str, int]:
        if any(amount < 0 for amount in v.values()):
            raise ValueError("All activity earning rules must be >= 0")
        return v

    @model_validator(mode="after")
    def tier_thresholds_ascending(self) -> "CreditConfigRequest":
        order = ["silver", "gold", "platinum"]
        values = [self.tier_thresholds.get(t, 0) for t in order]
        if values != sorted(values):
            raise ValueError("Tier thresholds must be ascending: silver < gold < platinum")
        return self

    @field_validator("tier_multipliers")
    @classmethod
    def multipliers_at_least_one(cls, v: dict[str, float]) -> dict[str, float]:
        if any(m < 1.0 for m in v.values()):
            raise ValueError("All tier multipliers must be >= 1.0")
        return v

    @field_validator("tier_discounts")
    @classmethod
    def discounts_in_range(cls, v: dict[str, float]) -> dict[str, float]:
        if any(d < 0.0 or d >= 1.0 for d in v.values()):
            raise ValueError("All tier discounts must be in [0.0, 1.0)")
        return v


class CreditConfigResponse(BaseModel):
    version: int
    is_active: bool
    default_initial_balance: int
    activity_earning_rules: dict[str, Any]
    service_costs: dict[str, Any]
    streak_bonus_7d: int
    streak_bonus_30d: int
    tier_thresholds: dict[str, Any]
    tier_multipliers: dict[str, Any]
    tier_discounts: dict[str, Any]
    created_by: str


@router.get("/credit-config", response_model=CreditConfigResponse)
async def get_credit_config(db: DbSession) -> Any:
    svc = ConfigService(db)
    config = await svc.get_active()
    return _to_response(config)


@router.put("/credit-config", response_model=CreditConfigResponse)
async def update_credit_config(body: CreditConfigRequest, db: DbSession) -> Any:
    svc = ConfigService(db)
    config = await svc.create_new_version(body.model_dump())
    return _to_response(config)


def _to_response(config) -> CreditConfigResponse:
    return CreditConfigResponse(
        version=config.version,
        is_active=config.is_active,
        default_initial_balance=config.default_initial_balance,
        activity_earning_rules=config.activity_earning_rules,
        service_costs=config.service_costs,
        streak_bonus_7d=config.streak_bonus_7d,
        streak_bonus_30d=config.streak_bonus_30d,
        tier_thresholds=config.tier_thresholds,
        tier_multipliers=config.tier_multipliers,
        tier_discounts=config.tier_discounts,
        created_by=config.created_by,
    )
