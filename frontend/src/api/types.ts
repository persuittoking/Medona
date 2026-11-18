export type Zone = "red" | "yellow" | "green";
export type Role = "nurse" | "doctor" | "specialist" | "department_head" | "district_admin" | "region_admin";
export const isAdmin = (r: Role | undefined) => r === "district_admin" || r === "region_admin";

export interface User {
  id: number;
  username: string;
  full_name: string;
  role: Role;
  polyclinic_id: number | null;
  region_id: number | null;
  district_id: number | null;
  polyclinic_code: string | null;
  polyclinic_name: string | null;
  district_name: string | null;
  region_name: string | null;
}

export interface Hit {
  code: string;
  zone: string;
  uz_text: string;
  /** trend hits (P01-P05): the series the rule used, for the sparkline */
  kind?: string | null;
  param?: string | null;
  values?: number[] | null;
  weeks?: number[] | null;
  dates?: string[] | null;
  direction?: "up" | "down" | null;
  unit?: string | null;
  projected?: number | null;
}
export interface ShapItem { feature: string; value: number | null; shap: number; direction: "up" | "down"; uz_label: string }

export interface Risk {
  id?: number | null;
  zone: Zone;
  ml_probability: number | null;
  rule_hits: Hit[];
  trend_hits: Hit[];
  notes: string[];
  shap_top: ShapItem[];
  model_version: string | null;
  explanation_uz: string;
  created_at?: string | null;
}

export interface Visit {
  id: number;
  visit_date: string;
  gestational_weeks: number;
  systolic: number | null;
  diastolic: number | null;
  proteinuria: string | null;
  hemoglobin_g_l: number | null;
  fasting_glucose_mmol: number | null;
  weight_kg: number | null;
  temperature_c: number | null;
  fetal_heart_rate: number | null;
  fundal_height_cm: number | null;
  symptoms: string[];
  notes: string | null;
}

export interface Alert {
  id: number;
  level: "red" | "yellow";
  status: "open" | "acknowledged" | "escalated" | "resolved";
  escalation_level: number;
  sla_due_at: string;
  created_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  action_taken: string | null;
  assigned_to: string | null;
  pregnancy_id: number | null;
  patient_id: number | null;
  patient_code: string | null;
  gestational_weeks: number | null;
  mahalla_name: string | null;
  reasons: string[];
  assigned_role: Role | null;
  assigned_user_id: number | null;
  next_role: Role | null;
  trend_driven: boolean;
  summary_status: "ready" | "pending" | "unavailable";
  summary_bullets: string[] | null;
  summary_source: "ai" | "template" | null;
  history: AlertEvent[];
}

export interface AlertEvent {
  at: string;
  event: "created" | "escalated" | "reassigned" | "acknowledged" | "resolved" | "admin_notified" | string;
  escalation_level: number;
  assignee: string | null;
  assignee_role: Role | null;
  actor: string | null;
  note: string | null;
}

export interface SlaSettings {
  demo_mode: boolean;
  sla_red_minutes: number;
  demo_sla_red_minutes: number;
  effective_sla_red_minutes: number;
  sla_yellow_hours: number;
  chain: Record<"red" | "yellow", Role[]>;
}

export interface PatientRow {
  patient_id: number;
  pregnancy_id: number;
  code: string;
  name_masked: string;
  age: number;
  gestational_weeks: number;
  trimester: number;
  zone: Zone;
  risk: number | null;
  last_visit_date: string | null;
  overdue: boolean;
  district_name: string;
  mahalla: string;
}

export interface Newborn {
  id: number;
  birth_date: string;
  gestational_weeks_at_birth: number;
  birth_weight_g: number;
  apgar_5: number | null;
  zone: Zone;
  hits: Hit[];
}

export interface PatientDetail {
  patient_id: number;
  code: string;
  name_masked: string;
  pinfl_masked: string;
  phone_masked: string;
  age: number;
  district_name: string;
  region_name: string;
  polyclinic_name: string;
  mahalla: string;
  mahalla_id: number;
  home: { lat: number; lon: number };
  distance_to_perinatal_km: number;
  nurse: string | null;
  pregnancy: {
    id: number;
    status: string;
    lmp_date: string;
    booking_date: string;
    gestational_weeks: number;
    edd: string;
    gravidity: number;
    parity: number;
    history: string[];
    current_zone: Zone;
    current_risk_score: number | null;
    bmi_booking: number | null;
    height_cm: number;
    booking_weight_kg: number;
  };
  latest_assessment: Risk | null;
  visits: Visit[];
  assessments: Risk[];
  alerts: Alert[];
  newborns: Newborn[];
}

export interface VisitCreated {
  visit: Visit;
  assessment: Risk;
  previous_zone: Zone;
  alert: Alert | null;
}

export interface Summary {
  active_pregnancies: number;
  red: number;
  yellow: number;
  green: number;
  open_alerts: number;
  open_red_alerts: number;
  sla_breaches: number;
  median_ack_minutes: number | null;
}


export interface TopRow {
  patient_id: number;
  pregnancy_id: number;
  code: string;
  name_masked: string;
  mahalla_name: string;
  gestational_weeks: number;
  zone: Zone;
  risk: number | null;
  main_reason: string | null;
}

export interface AiSummaryPending {
  status: "pending";
  risk_assessment_id: number;
}

export interface AiSummary {
  status: "ready";
  source: "ai" | "template";
  model: string | null;
  summary_uz: string;
  key_concerns: { code: string; text_uz: string }[];
  recommended_actions: { code: string; text_uz: string }[];
  questions_to_ask_patient_uz: string[];
  doctor_bullets_uz?: string[];
  disclaimer_uz: string;
  risk_assessment_id: number;
  generated_at: string;
}

export type GeoPolygon = { type: "Polygon"; coordinates: number[][][] };

export interface MahallaGeo {
  id: number;
  name: string;
  boundary: GeoPolygon;
  centroid: [number, number];
  demo_boundary: boolean;
  source: string;
}

export interface MapPoint {
  patient_id: number;
  pregnancy_id: number;
  code: string;
  zone: Zone;
  risk: number | null;
  lat: number;
  lon: number;
}

export interface PolyclinicMapData {
  polyclinic: { id: number; code: string; name: string; lat: number; lon: number };
  mahallas: MahallaGeo[];
  points: MapPoint[];
}

export interface Territory {
  code: string;
  name: string;
  district: string;
  mahallas: { name: string; boundary: GeoPolygon }[];
}

export interface Agg {
  red: number;
  yellow: number;
  green: number;
  total: number;
  red_share: number;
  open_alerts: number;
}

export interface GeoNode extends Partial<Agg> {
  id: number;
  name: string;
  code?: string;
  lat: number;
  lon: number;
  accessible: boolean;
  polyclinics?: number;
  territory?: { name: string; boundary: GeoPolygon }[];
}

export interface Crumb { level: string; id?: number; name: string }

export interface GeoLevel {
  level: "country" | "region" | "district";
  id?: number;
  name: string;
  children: GeoNode[];
  breadcrumb?: Crumb[];
}

export interface GeoPolyclinic extends Agg {
  level: "polyclinic";
  id: number;
  code: string;
  name: string;
  lat: number;
  lon: number;
  territory: { name: string; boundary: GeoPolygon }[];
  breadcrumb: Crumb[];
}
