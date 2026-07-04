from typing import Literal, Optional

from pydantic import BaseModel, Field


RiskLevel = Literal["normal", "medium", "high", "critical"]
RoadStatus = Literal["open", "slow", "blocked", "unknown"]
SourceType = Literal["warehouse", "clinic"]


class ClinicBase(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    test_kits_available: int = Field(ge=0)
    people_waiting: int = Field(ge=0)
    nurses_available: int = Field(ge=0)
    threshold_min_kits: int = Field(ge=0)


class Clinic(ClinicBase):
    testing_capacity_per_hour: int
    queue_delay_hours: Optional[float]
    operations_remaining_hours: Optional[float]
    risk_level: RiskLevel
    last_updated_at: str
    last_computed_at: str


class ClinicUpdate(BaseModel):
    test_kits_available: Optional[int] = Field(default=None, ge=0)
    people_waiting: Optional[int] = Field(default=None, ge=0)
    nurses_available: Optional[int] = Field(default=None, ge=0)
    threshold_min_kits: Optional[int] = Field(default=None, ge=0)


class Warehouse(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    test_kits_stock: int = Field(ge=0)
    last_updated_at: str


class WarehouseUpdate(BaseModel):
    test_kits_stock: int = Field(ge=0)


class ResupplyOption(BaseModel):
    source_id: str
    source_name: str
    source_type: SourceType
    available_stock: int
    delivery_time_minutes: int
    road_status: RoadStatus
    recommended_transfer_quantity: int
    supplier_remaining_stock_after_transfer: int
    supplier_operations_remaining_after_transfer: Optional[float]
    is_safe_for_supplier: bool
    can_fully_supply: bool
    rank: int
    reason: str


class AgentRecommendation(BaseModel):
    clinic_id: str
    clinic: str
    status: RiskLevel
    reasoning: list[str]
    recommendation: str
    options: list[ResupplyOption]


class Alert(BaseModel):
    clinic_id: str
    clinic: str
    risk_level: RiskLevel
    operations_remaining_hours: Optional[float]
    queue_delay_hours: Optional[float]
    reason: str
