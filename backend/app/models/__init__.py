"""ORM models. *_enc columns hold Fernet-encrypted PII."""
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Region(Base):
    __tablename__ = "regions"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    districts: Mapped[list["District"]] = relationship(back_populates="region")


class District(Base):
    __tablename__ = "districts"
    id: Mapped[int] = mapped_column(primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"))
    code: Mapped[str] = mapped_column(String(8))
    name: Mapped[str] = mapped_column(String(120))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    region: Mapped[Region] = relationship(back_populates="districts")


class Polyclinic(Base):
    """Oilaviy poliklinika: the TENANT. Serves 1..N mahallas."""
    __tablename__ = "polyclinics"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)  # e.g. PL-NUK-001
    name: Mapped[str] = mapped_column(String(160))
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"), index=True)
    address: Mapped[str] = mapped_column(String(200))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    district: Mapped[District] = relationship()
    mahallas: Mapped[list["Mahalla"]] = relationship(back_populates="polyclinic")


class Mahalla(Base):
    __tablename__ = "mahallas"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    polyclinic_id: Mapped[int] = mapped_column(ForeignKey("polyclinics.id"), index=True)
    boundary_geojson: Mapped[dict] = mapped_column(JSON)  # GeoJSON Polygon geometry (lon, lat)
    boundary_source: Mapped[str] = mapped_column(String(200))
    demo_boundary: Mapped[bool] = mapped_column(Boolean, default=True)
    centroid_lat: Mapped[float] = mapped_column(Float)
    centroid_lon: Mapped[float] = mapped_column(Float)
    polyclinic: Mapped[Polyclinic] = relationship(back_populates="mahallas")


# department_head = OvaBMU bo'lim mudiri: receives RED alerts a specialist did not acknowledge in time.
POLYCLINIC_ROLES = ("nurse", "doctor", "specialist", "department_head")
ADMIN_ROLES = ("district_admin", "region_admin")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("polyclinic_id", "username", name="uq_user_polyclinic_username"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64))
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(16))  # POLYCLINIC_ROLES | district_admin | region_admin
    polyclinic_id: Mapped[int | None] = mapped_column(ForeignKey("polyclinics.id"), index=True)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"))
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"))
    telegram_chat_id: Mapped[str | None] = mapped_column(String(32))
    password_hash: Mapped[str] = mapped_column(String(128))


class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    full_name_enc: Mapped[str] = mapped_column(Text)
    pinfl_enc: Mapped[str] = mapped_column(Text)
    phone_enc: Mapped[str] = mapped_column(Text)
    home_enc: Mapped[str] = mapped_column(Text)  # encrypted "lat,lon" — personal data, own polyclinic only
    birth_date: Mapped[date] = mapped_column(Date)
    polyclinic_id: Mapped[int] = mapped_column(ForeignKey("polyclinics.id"), index=True)  # tenant key
    mahalla_id: Mapped[int] = mapped_column(ForeignKey("mahallas.id"), index=True)
    distance_to_perinatal_km: Mapped[float] = mapped_column(Float)
    assigned_nurse_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    polyclinic: Mapped[Polyclinic] = relationship()
    mahalla: Mapped[Mahalla] = relationship()
    pregnancies: Mapped[list["Pregnancy"]] = relationship(back_populates="patient")


class Pregnancy(Base):
    __tablename__ = "pregnancies"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    lmp_date: Mapped[date] = mapped_column(Date)
    booking_date: Mapped[date] = mapped_column(Date)
    gravidity: Mapped[int] = mapped_column(Integer, default=1)
    parity: Mapped[int] = mapped_column(Integer, default=0)
    previous_cs: Mapped[bool] = mapped_column(Boolean, default=False)
    hist_stillbirth: Mapped[bool] = mapped_column(Boolean, default=False)
    hist_preterm: Mapped[bool] = mapped_column(Boolean, default=False)
    miscarriages_count: Mapped[int] = mapped_column(Integer, default=0)
    hist_preeclampsia: Mapped[bool] = mapped_column(Boolean, default=False)
    hist_pph: Mapped[bool] = mapped_column(Boolean, default=False)
    diabetes: Mapped[bool] = mapped_column(Boolean, default=False)
    chronic_htn: Mapped[bool] = mapped_column(Boolean, default=False)
    heart: Mapped[bool] = mapped_column(Boolean, default=False)
    kidney: Mapped[bool] = mapped_column(Boolean, default=False)
    thyroid: Mapped[bool] = mapped_column(Boolean, default=False)
    epilepsy: Mapped[bool] = mapped_column(Boolean, default=False)
    multiple_pregnancy: Mapped[bool] = mapped_column(Boolean, default=False)
    rh_negative: Mapped[bool] = mapped_column(Boolean, default=False)
    interpregnancy_months: Mapped[int | None] = mapped_column(Integer)
    height_cm: Mapped[float] = mapped_column(Float)
    booking_weight_kg: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    current_zone: Mapped[str] = mapped_column(String(8), default="green", index=True)
    current_risk_score: Mapped[float | None] = mapped_column(Float)
    patient: Mapped[Patient] = relationship(back_populates="pregnancies")
    visits: Mapped[list["Visit"]] = relationship(back_populates="pregnancy", order_by="Visit.visit_date")
    newborns: Mapped[list["Newborn"]] = relationship(back_populates="pregnancy")


class Visit(Base):
    __tablename__ = "visits"
    id: Mapped[int] = mapped_column(primary_key=True)
    pregnancy_id: Mapped[int] = mapped_column(ForeignKey("pregnancies.id"), index=True)
    visit_date: Mapped[date] = mapped_column(Date)
    gestational_weeks: Mapped[float] = mapped_column(Float)
    systolic: Mapped[int | None] = mapped_column(Integer)
    diastolic: Mapped[int | None] = mapped_column(Integer)
    proteinuria: Mapped[str | None] = mapped_column(String(8))  # neg | trace | +1 | +2 | +3
    hemoglobin_g_l: Mapped[float | None] = mapped_column(Float)
    fasting_glucose_mmol: Mapped[float | None] = mapped_column(Float)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    temperature_c: Mapped[float | None] = mapped_column(Float)
    fetal_heart_rate: Mapped[int | None] = mapped_column(Integer)
    fundal_height_cm: Mapped[float | None] = mapped_column(Float)
    symptoms: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    entered_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    pregnancy: Mapped[Pregnancy] = relationship(back_populates="visits")


class Newborn(Base):
    __tablename__ = "newborns"
    id: Mapped[int] = mapped_column(primary_key=True)
    pregnancy_id: Mapped[int] = mapped_column(ForeignKey("pregnancies.id"), index=True)
    birth_date: Mapped[date] = mapped_column(Date)
    gestational_weeks_at_birth: Mapped[float] = mapped_column(Float)
    birth_weight_g: Mapped[int] = mapped_column(Integer)
    apgar_5: Mapped[int | None] = mapped_column(Integer)
    current_zone: Mapped[str] = mapped_column(String(8), default="green")
    pregnancy: Mapped[Pregnancy] = relationship(back_populates="newborns")
    checks: Mapped[list["NewbornCheck"]] = relationship(back_populates="newborn", order_by="NewbornCheck.check_date")


class NewbornCheck(Base):
    __tablename__ = "newborn_checks"
    id: Mapped[int] = mapped_column(primary_key=True)
    newborn_id: Mapped[int] = mapped_column(ForeignKey("newborns.id"), index=True)
    check_date: Mapped[date] = mapped_column(Date)
    not_feeding_well: Mapped[bool] = mapped_column(Boolean, default=False)
    convulsions: Mapped[bool] = mapped_column(Boolean, default=False)
    resp_rate: Mapped[int | None] = mapped_column(Integer)
    severe_chest_indrawing: Mapped[bool] = mapped_column(Boolean, default=False)
    temperature_c: Mapped[float | None] = mapped_column(Float)
    movement_only_when_stimulated: Mapped[bool] = mapped_column(Boolean, default=False)
    jaundice_first_24h: Mapped[bool] = mapped_column(Boolean, default=False)
    jaundice_palms_soles: Mapped[bool] = mapped_column(Boolean, default=False)
    weight_g: Mapped[int | None] = mapped_column(Integer)
    newborn: Mapped[Newborn] = relationship(back_populates="checks")


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"
    id: Mapped[int] = mapped_column(primary_key=True)
    pregnancy_id: Mapped[int | None] = mapped_column(ForeignKey("pregnancies.id"), index=True)
    newborn_id: Mapped[int | None] = mapped_column(ForeignKey("newborns.id"), index=True)
    visit_id: Mapped[int | None] = mapped_column(ForeignKey("visits.id"))
    check_id: Mapped[int | None] = mapped_column(ForeignKey("newborn_checks.id"))
    zone: Mapped[str] = mapped_column(String(8))
    rule_hits: Mapped[list] = mapped_column(JSON, default=list)
    trend_hits: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[list] = mapped_column(JSON, default=list)
    ml_probability: Mapped[float | None] = mapped_column(Float)
    shap_top: Mapped[list] = mapped_column(JSON, default=list)
    model_version: Mapped[str | None] = mapped_column(String(32))
    explanation_uz: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    risk_assessment_id: Mapped[int] = mapped_column(ForeignKey("risk_assessments.id"))
    pregnancy_id: Mapped[int | None] = mapped_column(ForeignKey("pregnancies.id"), index=True)
    level: Mapped[str] = mapped_column(String(8))  # red | yellow
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)
    sla_due_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    action_taken: Mapped[str | None] = mapped_column(Text)
    risk_assessment: Mapped[RiskAssessment] = relationship()
    pregnancy: Mapped[Pregnancy | None] = relationship()
    events: Mapped[list["AlertEvent"]] = relationship(back_populates="alert", order_by="AlertEvent.id")


class AlertEvent(Base):
    """Escalation history of one alert: who it was assigned to, when, and by whom (actor None = system)."""
    __tablename__ = "alert_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"), index=True)
    event: Mapped[str] = mapped_column(String(20))  # created | escalated | reassigned | acknowledged | resolved | admin_notified
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    alert: Mapped[Alert] = relationship(back_populates="events")


class LlmSummaryCache(Base):
    __tablename__ = "llm_summaries"
    id: Mapped[int] = mapped_column(primary_key=True)
    risk_assessment_id: Mapped[int] = mapped_column(ForeignKey("risk_assessments.id"), unique=True)
    source: Mapped[str] = mapped_column(String(16))  # ai | template
    payload: Mapped[dict] = mapped_column(JSON)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(48))
    entity: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


Index("ix_visits_preg_date", Visit.pregnancy_id, Visit.visit_date)
Index("ix_patients_tenant", Patient.polyclinic_id, Patient.id)
