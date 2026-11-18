export type Zone = "red" | "yellow" | "green";
/** What a screen shows: pregnant women, children 0-12 months, or both (the "Homiladorlar | Bolalar | Hammasi" switch). */
export type Subject = "pregnancy" | "child" | "all";
export type SubjectCounts = Record<Subject, number>;
export type Role = "nurse" | "doctor" | "specialist" | "department_head" | "district_admin" | "region_admin";
export const isAdmin = (r: Role | undefined) => r === "district_admin" || r === "region_admin";

export interface User {
  id: number;
  username: string;
  full_name: string;
  role: Role;
  polyclinic_id: number | null;
  mahalla_id: number | null;
  region_id: number | null;
  district_id: number | null;
  polyclinic_code: string | null;
  polyclinic_name: string | null;
  mahalla_name: string | null;
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
  /** infant growth trends (G01/G02): the child's age at each point */
  ages_months?: number[] | null;
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
  entered_by?: number | null;
  performed_at_polyclinic_id?: number | null;
  performed_at_polyclinic_name?: string | null;
  performed_at_polyclinic_code?: string | null;
  external_badge_uz?: string | null;
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
  subject: "pregnancy" | "child";
  /** "Homilador · 32 hafta" | "Bola · 4 oy" */
  subject_label: string | null;
  newborn_id: number | null;
  child_age_days: number | null;
  assigned_role: Role | null;
  assigned_user_id: number | null;
  next_role: Role | null;
  trend_driven: boolean;
  summary_status: "ready" | "pending" | "unavailable";
  summary_bullets: string[] | null;
  summary_source: "ai" | "template" | null;
  performed_at_polyclinic_name?: string | null;
  external_notice_uz?: string | null;
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
  mahalla_id?: number | null;
}

export interface Newborn {
  id: number;
  code: string | null;
  sex: Sex | null;
  status: string;
  age_days: number | null;
  pregnancy_id: number | null;
  birth_date: string;
  gestational_weeks_at_birth: number;
  birth_weight_g: number;
  apgar_5: number | null;
  zone: Zone;
  hits: Hit[];
}

export interface ScheduledVisit {
  visit_number: number;
  target_week: number;
  status: "completed" | "upcoming";
  recommended_intensity: "To'liq" | "Yengil";
  intensity: "To'liq" | "Yengil";
  intensity_code: "full" | "light";
}

export interface VisitPlan {
  standard_visits: number;
  total_scheduled_visits: number;
  eligible: boolean;
  confirmed: boolean;
  confirmed_by: string | null;
  confirmed_at: string | null;
  consecutive_green: number;
  consecutive_green_required: number;
  light_visit_max_weeks: number;
  recommendation_uz: string | null;
  reason_uz: string;
  recommended_light_visits: number;
  confirmed_light_visits: number;
  schedule: ScheduledVisit[];
}

export interface VisitIntensityImpact {
  standard_visits: number;
  eligible_pregnancies: number;
  confirmed_pregnancies: number;
  confirmed_light_visits: number;
  minutes_per_light_visit: number;
  saved_doctor_minutes: number;
  label_uz: string;
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
  visit_plan?: VisitPlan | null;
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
  subject: Subject;
  /** active subjects of the chosen kind */
  active: number;
  active_pregnancies: number;
  active_children: number;
  counts: SubjectCounts;
  red: number;
  yellow: number;
  green: number;
  open_alerts: number;
  open_red_alerts: number;
  sla_breaches: number;
  median_ack_minutes: number | null;
  confirmed_light_visits?: number;
  minutes_per_light_visit?: number;
  saved_doctor_minutes?: number;
  visit_intensity_impact?: VisitIntensityImpact;
}


export interface TopRow {
  subject: "pregnancy" | "child";
  patient_id: number;
  pregnancy_id: number | null;
  newborn_id: number | null;
  code: string;
  name_masked: string | null;
  mahalla_name: string;
  gestational_weeks: number | null;
  child_age_days: number | null;
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

export interface MahallaGeo extends Partial<Agg> {
  id: number;
  name: string;
  boundary: GeoPolygon;
  centroid: [number, number];
  demo_boundary: boolean;
  source: string;
}

export interface MapPoint {
  kind: "pregnancy" | "child";
  patient_id: number;
  pregnancy_id: number | null;
  newborn_id: number | null;
  code: string;
  zone: Zone;
  risk: number | null;
  lat: number;
  lon: number;
  mahalla_id?: number;
}

export interface PolyclinicMapData {
  polyclinic: { id: number; code: string; name: string; lat: number; lon: number };
  mahallas: MahallaGeo[];
  points: MapPoint[];
  /** true for role nurse: the server returned red-zone points only (counts stay aggregate) */
  red_only?: boolean;
  /** aggregate totals per subject for this polyclinic (all zones) */
  subject_counts?: SubjectCounts;
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
  subject_counts: SubjectCounts;
  id?: number;
  name: string;
  children: GeoNode[];
  breadcrumb?: Crumb[];
}

export interface GeoPolyclinic extends Agg {
  level: "polyclinic";
  subject_counts: SubjectCounts;
  id: number;
  code: string;
  name: string;
  lat: number;
  lon: number;
  territory: ({ id?: number; name: string; boundary: GeoPolygon } & Partial<Agg>)[];
  mahallas?: ({ id: number; name: string; boundary: GeoPolygon } & Agg)[];
  breadcrumb: Crumb[];
}

export interface PolyclinicSearchMahalla extends Agg {
  id: number;
  name: string;
  boundary: GeoPolygon;
  centroid: [number, number];
}

export interface PolyclinicSearchItem extends Agg {
  id: number;
  code: string;
  name: string;
  city: string;
  region_name: string;
  lat: number;
  lon: number;
  mahalla_count: number;
  mahallas: PolyclinicSearchMahalla[];
}

// ---------------- children 0-12 months ("Bolalar") ----------------
export type Sex = "m" | "f";
export type Feeding = "exclusive_breast" | "mixed" | "formula" | "complementary";

export interface ChildRow {
  newborn_id: number;
  code: string;
  mother_patient_id: number;
  mother_code: string;
  sex: Sex | null;
  age_days: number;
  zone: Zone;
  risk: number | null;
  last_check_date: string | null;
  overdue: boolean;
  mahalla: string;
  mahalla_id?: number | null;
  main_reason: string | null;
}

export interface ChildCheck {
  id: number;
  check_date: string;
  age_days: number | null;
  weight_g: number | null;
  length_cm: number | null;
  head_circ_cm: number | null;
  resp_rate: number | null;
  temperature_c: number | null;
  feeding: Feeding | null;
  not_feeding_well: boolean | null;
  vomiting_everything: boolean | null;
  convulsions: boolean | null;
  lethargic: boolean | null;
  movement_only_when_stimulated: boolean | null;
  severe_chest_indrawing: boolean | null;
  jaundice_first_24h: boolean | null;
  jaundice_palms_soles: boolean | null;
  blood_in_stool: boolean | null;
  diarrhoea_days: number | null;
  cough_days: number | null;
  vaccines_given: string[] | null;
  vaccines_due_overdue: string[] | null;
  notes: string | null;
  entered_by?: number | null;
  performed_at_polyclinic_id?: number | null;
  performed_at_polyclinic_name?: string | null;
  performed_at_polyclinic_code?: string | null;
  external_badge_uz?: string | null;
}

export interface Vaccine {
  code: string;
  family: string;
  due_date: string;
  status: "given" | "overdue" | "due" | "upcoming";
  days_late: number;
}

export interface GrowthPoint {
  age_months: number;
  weight_kg?: number | null;
  z?: number | null;
  median?: number | null;
  minus2sd?: number | null;
}

export interface ChildDetail {
  newborn_id: number;
  code: string;
  sex: Sex | null;
  status: string;
  birth_date: string;
  age_days: number;
  gestational_weeks_at_birth: number;
  birth_weight_g: number;
  apgar_5: number | null;
  zone: Zone;
  mother_patient_id: number;
  mother_code: string;
  mahalla: string;
  polyclinic_name: string;
  latest_assessment: Risk | null;
  checks: ChildCheck[];
  assessments: Risk[];
  alerts: Alert[];
  growth: GrowthPoint[];
  reference: GrowthPoint[];
  vaccines: Vaccine[];
}

export interface ChildCheckCreated {
  check: ChildCheck;
  assessment: Risk;
  previous_zone: Zone;
  alert: Alert | null;
}

export interface ExternalLookupOut {
  patient_code: string;
  responsible_polyclinic_id: number;
  responsible_polyclinic_code: string;
  responsible_polyclinic_name: string;
  mahalla_name: string;
  has_active_pregnancy: boolean;
  children: { newborn_id: number; code: string }[];
}

export interface ExternalEntryOut {
  id: number;
  subject: "pregnancy" | "child";
  patient_code: string;
  responsible_polyclinic_id: number;
  responsible_polyclinic_code: string;
  responsible_polyclinic_name: string;
  mahalla_name: string;
  performed_at_polyclinic_id: number | null;
  performed_at_polyclinic_name: string;
  message_uz: string;
}

export interface ExternalNotification {
  kind: "pregnancy" | "child";
  id: number;
  patient_id: number;
  pregnancy_id: number | null;
  newborn_id: number | null;
  code: string;
  mahalla: string;
  visit_date: string;
  created_at: string;
  performed_at_polyclinic_id: number;
  performed_at_polyclinic_code: string;
  performed_at_polyclinic_name: string;
  notice_uz: string;
  badge_uz: string;
}
