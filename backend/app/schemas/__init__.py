"""Pydantic v2 request/response schemas (the API contract: docs/openapi_contract.md)."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.risk.features import SYMPTOMS

Zone = Literal["red", "yellow", "green"]
Role = Literal["nurse", "doctor", "specialist", "department_head", "district_admin", "region_admin"]
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
    mahalla_id: int | None = None
    region_id: int | None
    district_id: int | None
    polyclinic_code: str | None = None
    polyclinic_name: str | None = None
    mahalla_name: str | None = None
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
    # trend hits (kind "trend"): the series the rule used, for the sparkline (P01-P05)
    kind: str | None = None
    param: str | None = None
    values: list[float] | None = None
    weeks: list[float] | None = None
    dates: list[date] | None = None
    direction: Literal["up", "down"] | None = None
    unit: str | None = None
    projected: float | None = None
    horizon_weeks: float | None = None
    ages_months: list[float] | None = None  # infant growth trends (G01/G02): child's age at each point


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
    entered_by: int | None = None
    performed_at_polyclinic_id: int | None = None
    performed_at_polyclinic_name: str | None = None
    performed_at_polyclinic_code: str | None = None
    external_badge_uz: str | None = None


class AlertEventOut(BaseModel):
    at: datetime
    event: str
    escalation_level: int
    assignee: str | None
    assignee_role: str | None
    actor: str | None
    note: str | None


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
    patient_id: int | None  # the mother's patient id (also for a child alert)
    patient_code: str | None  # pseudonymous code of the subject (mother "QQR-..." or child "B-...")
    gestational_weeks: float | None
    mahalla_name: str | None
    reasons: list[str]
    subject: Literal["pregnancy", "child"] = "pregnancy"
    subject_label: str | None = None  # "Homilador · 32 hafta" | "Bola · 4 oy"
    newborn_id: int | None = None
    child_age_days: int | None = None
    assigned_role: str | None = None
    assigned_user_id: int | None = None
    next_role: str | None = None
    trend_driven: bool = False
    summary_status: Literal["ready", "pending", "unavailable"] = "pending"
    summary_bullets: list[str] | None = None
    summary_source: Literal["ai", "template"] | None = None
    performed_at_polyclinic_name: str | None = None
    external_notice_uz: str | None = None
    history: list[AlertEventOut] = []


class VisitCreatedOut(BaseModel):
    visit: VisitOut
    assessment: RiskOut
    previous_zone: Zone
    alert: AlertOut | None


class ActionIn(BaseModel):
    action_taken: str = Field(min_length=3, max_length=500)


class ReassignIn(BaseModel):
    user_id: int
    note: str | None = Field(None, max_length=300)


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
    mahalla_id: int | None = None


class NewbornOut(BaseModel):
    """A child of this mother (on the mother's card)."""
    id: int
    code: str | None = None
    sex: str | None = None
    status: str = "active"
    age_days: int | None = None
    pregnancy_id: int | None = None
    birth_date: date
    gestational_weeks_at_birth: float
    birth_weight_g: int
    apgar_5: int | None
    zone: Zone
    hits: list[Hit]


Feeding = Literal["exclusive_breast", "mixed", "formula", "complementary"]


class ChildCheckIn(BaseModel):
    """An infant check (0-12 months). Booleans default to "not present"."""
    newborn_id: int
    check_date: date | None = None
    weight_g: int | None = Field(None, ge=500, le=16000)
    length_cm: float | None = Field(None, ge=30, le=95)
    head_circ_cm: float | None = Field(None, ge=20, le=55)
    resp_rate: int | None = Field(None, ge=10, le=120)
    temperature_c: float | None = Field(None, ge=33, le=43)
    feeding: Feeding | None = None
    not_feeding_well: bool = False
    vomiting_everything: bool = False
    convulsions: bool = False
    lethargic: bool = False
    movement_only_when_stimulated: bool = False
    severe_chest_indrawing: bool = False
    jaundice_first_24h: bool = False
    jaundice_palms_soles: bool = False
    blood_in_stool: bool = False
    diarrhoea_days: int | None = Field(None, ge=0, le=60)
    cough_days: int | None = Field(None, ge=0, le=120)
    vaccines_given: list[str] = []
    notes: str | None = Field(None, max_length=2000)


class ChildCheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    check_date: date
    age_days: int | None
    weight_g: int | None
    length_cm: float | None
    head_circ_cm: float | None
    resp_rate: int | None
    temperature_c: float | None
    feeding: str | None
    not_feeding_well: bool | None
    vomiting_everything: bool | None
    convulsions: bool | None
    lethargic: bool | None
    movement_only_when_stimulated: bool | None
    severe_chest_indrawing: bool | None
    jaundice_first_24h: bool | None
    jaundice_palms_soles: bool | None
    blood_in_stool: bool | None
    diarrhoea_days: int | None
    cough_days: int | None
    vaccines_given: list[str] | None
    vaccines_due_overdue: list[str] | None
    notes: str | None
    entered_by: int | None = None
    performed_at_polyclinic_id: int | None = None
    performed_at_polyclinic_name: str | None = None
    performed_at_polyclinic_code: str | None = None
    external_badge_uz: str | None = None


class ChildRow(BaseModel):
    newborn_id: int
    code: str
    mother_patient_id: int
    mother_code: str
    sex: str | None
    age_days: int
    zone: Zone
    risk: float | None
    last_check_date: date | None
    overdue: bool
    mahalla: str
    mahalla_id: int | None = None
    main_reason: str | None


class VaccineOut(BaseModel):
    code: str
    family: str
    due_date: date
    status: Literal["given", "overdue", "due", "upcoming"]
    days_late: int


class GrowthPoint(BaseModel):
    age_months: float
    weight_kg: float | None = None
    z: float | None = None
    median: float | None = None
    minus2sd: float | None = None


class ChildDetail(BaseModel):
    newborn_id: int
    code: str
    sex: str | None
    status: str
    birth_date: date
    age_days: int
    gestational_weeks_at_birth: float
    birth_weight_g: int
    apgar_5: int | None
    zone: Zone
    mother_patient_id: int
    mother_code: str
    mahalla: str
    polyclinic_name: str
    latest_assessment: RiskOut | None
    checks: list[ChildCheckOut]
    assessments: list[RiskOut]
    alerts: list[AlertOut]
    growth: list[GrowthPoint]
    reference: list[GrowthPoint]
    vaccines: list[VaccineOut]


class ChildCheckCreatedOut(BaseModel):
    check: ChildCheckOut
    assessment: RiskOut
    previous_zone: Zone
    alert: AlertOut | None


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


class ScheduledVisitOut(BaseModel):
    visit_number: int
    target_week: int
    status: Literal["completed", "upcoming"]
    recommended_intensity: Literal["To'liq", "Yengil"]
    intensity: Literal["To'liq", "Yengil"]
    intensity_code: Literal["full", "light"]


class VisitPlanOut(BaseModel):
    standard_visits: int = 12
    total_scheduled_visits: int = 12
    eligible: bool
    confirmed: bool
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    consecutive_green: int
    consecutive_green_required: int
    light_visit_max_weeks: float
    recommendation_uz: str | None = None
    reason_uz: str
    recommended_light_visits: int
    confirmed_light_visits: int
    schedule: list[ScheduledVisitOut]


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
    visit_plan: VisitPlanOut | None = None
    latest_assessment: RiskOut | None
    visits: list[VisitOut]
    assessments: list[RiskOut]
    alerts: list[AlertOut]
    newborns: list[NewbornOut]


class PiiOut(BaseModel):
    full_name: str
    pinfl: str
    phone: str


class ExternalLookupIn(BaseModel):
    pinfl: str = Field(min_length=4, max_length=32)


class ExternalChildItem(BaseModel):
    newborn_id: int
    code: str


class ExternalLookupOut(BaseModel):
    """Minimum-necessary view for an external polyclinic: NO name, history, zone or address."""
    patient_code: str
    responsible_polyclinic_id: int
    responsible_polyclinic_code: str
    responsible_polyclinic_name: str
    mahalla_name: str
    has_active_pregnancy: bool
    children: list[ExternalChildItem] = []


class ExternalVisitIn(BaseModel):
    pinfl: str | None = Field(None, min_length=4, max_length=32)
    pregnancy_id: int | None = None
    patient_code: str | None = None
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


class ExternalCheckIn(BaseModel):
    pinfl: str | None = Field(None, min_length=4, max_length=32)
    newborn_id: int | None = None
    child_code: str | None = None
    check_date: date | None = None
    weight_g: int | None = Field(None, ge=500, le=16000)
    length_cm: float | None = Field(None, ge=30, le=95)
    head_circ_cm: float | None = Field(None, ge=20, le=55)
    resp_rate: int | None = Field(None, ge=10, le=120)
    temperature_c: float | None = Field(None, ge=33, le=43)
    feeding: Feeding | None = None
    not_feeding_well: bool = False
    vomiting_everything: bool = False
    convulsions: bool = False
    lethargic: bool = False
    movement_only_when_stimulated: bool = False
    severe_chest_indrawing: bool = False
    jaundice_first_24h: bool = False
    jaundice_palms_soles: bool = False
    blood_in_stool: bool = False
    diarrhoea_days: int | None = Field(None, ge=0, le=60)
    cough_days: int | None = Field(None, ge=0, le=120)
    vaccines_given: list[str] = []
    notes: str | None = Field(None, max_length=2000)


class ExternalEntryOut(BaseModel):
    """Minimum-necessary confirmation after saving an external visit or infant check."""
    id: int
    subject: Literal["pregnancy", "child"] = "pregnancy"
    patient_code: str
    responsible_polyclinic_id: int
    responsible_polyclinic_code: str
    responsible_polyclinic_name: str
    mahalla_name: str
    performed_at_polyclinic_id: int | None
    performed_at_polyclinic_name: str
    message_uz: str
