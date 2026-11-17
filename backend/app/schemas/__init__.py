"""Pydantic v2 request/response schemas (the API contract: docs/openapi_contract.md)."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.risk.features import SYMPTOMS

Zone = Literal["red", "yellow", "green"]
Role = Literal["nurse", "doctor", "specialist", "district_admin", "region_admin"]
Proteinuria = Literal["neg", "trace", "+1", "+2", "+3"]
Symptom = Literal[tuple(SYMPTOMS)]  # type: ignore[valid-type]


class LoginIn(BaseModel):
    polyclinic_code: str | None = None  # required for polyclinic staff, empty for district/region admins
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    full_name: str
    role: Role
    polyclinic_id: int | None
    region_id: int | None
    district_id: int | None
    polyclinic_code: str | None = None
    polyclinic_name: str | None = None
    district_name: str | None = None
    region_name: str | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class Hit(BaseModel):
    code: str
    zone: str
    uz_text: str


class ShapItem(BaseModel):
    feature: str
    value: float | None
    shap: float
    direction: Literal["up", "down"]
    uz_label: str


class RiskOut(BaseModel):
    id: int | None = None
    zone: Zone
    ml_probability: float | None
    rule_hits: list[Hit]
    trend_hits: list[Hit]
    notes: list[str] = []
    shap_top: list[ShapItem]
    model_version: str | None
    explanation_uz: str
    created_at: datetime | None = None


class VisitIn(BaseModel):
    pregnancy_id: int
    visit_date: date | None = None
    systolic: int | None = Field(None, ge=60, le=260)
    diastolic: int | None = Field(None, ge=30, le=180)
    proteinuria: Proteinuria | None = None
    hemoglobin_g_l: float | None = Field(None, ge=30, le=200)
    fasting_glucose_mmol: float | None = Field(None, ge=1.5, le=35)
    weight_kg: float | None = Field(None, ge=30, le=200)
    temperature_c: float | None = Field(None, ge=33, le=43)
    fetal_heart_rate: int | None = Field(None, ge=50, le=240)
    fundal_height_cm: float | None = Field(None, ge=5, le=50)
    symptoms: list[Symptom] = []
    notes: str | None = Field(None, max_length=2000)


class VisitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    visit_date: date
    gestational_weeks: float
    systolic: int | None
    diastolic: int | None
    proteinuria: str | None
    hemoglobin_g_l: float | None
    fasting_glucose_mmol: float | None
    weight_kg: float | None
    temperature_c: float | None
    fetal_heart_rate: int | None
    fundal_height_cm: float | None
    symptoms: list[str]
    notes: str | None


class AlertOut(BaseModel):
    id: int
    level: Literal["red", "yellow"]
    status: Literal["open", "acknowledged", "escalated", "resolved"]
    escalation_level: int
    sla_due_at: datetime
    created_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    action_taken: str | None
    assigned_to: str | None
    pregnancy_id: int | None
    patient_id: int | None
    patient_code: str | None
    gestational_weeks: float | None
    mahalla_name: str | None
    reasons: list[str]


class VisitCreatedOut(BaseModel):
    visit: VisitOut
    assessment: RiskOut
    previous_zone: Zone
    alert: AlertOut | None


class ActionIn(BaseModel):
    action_taken: str = Field(min_length=3, max_length=500)


class PatientRow(BaseModel):
    patient_id: int
    pregnancy_id: int
    code: str
    name_masked: str
    age: int
    gestational_weeks: float
    trimester: int
    zone: Zone
    risk: float | None
    last_visit_date: date | None
    overdue: bool
    district_name: str
    mahalla: str


class NewbornOut(BaseModel):
    id: int
    birth_date: date
    gestational_weeks_at_birth: float
    birth_weight_g: int
    apgar_5: int | None
    zone: Zone
    hits: list[Hit]


class PregnancyOut(BaseModel):
    id: int
    status: str
    lmp_date: date
    booking_date: date
    gestational_weeks: float
    edd: date
    gravidity: int
    parity: int
    history: list[str]
    current_zone: Zone
    current_risk_score: float | None
    bmi_booking: float | None
    height_cm: float
    booking_weight_kg: float


class PatientDetail(BaseModel):
    patient_id: int
    code: str
    name_masked: str
    pinfl_masked: str
    phone_masked: str
    age: int
    district_name: str
    region_name: str
    polyclinic_name: str
    mahalla: str
    mahalla_id: int
    home: dict[str, float]
    distance_to_perinatal_km: float
    nurse: str | None
    pregnancy: PregnancyOut
    latest_assessment: RiskOut | None
    visits: list[VisitOut]
    assessments: list[RiskOut]
    alerts: list[AlertOut]
    newborns: list[NewbornOut]


class PiiOut(BaseModel):
    full_name: str
    pinfl: str
    phone: str
