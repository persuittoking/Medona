// All user-facing labels (Uzbek, Latin script).
import type { Role, Zone } from "../api/types";

export const ZONE_LABEL: Record<Zone, string> = { red: "Qizil", yellow: "Sariq", green: "Yashil" };
export const ZONE_COLOR: Record<Zone, string> = { red: "#DC2626", yellow: "#F59E0B", green: "#16A34A" };

export const ROLE_LABEL: Record<Role, string> = {
  nurse: "Patronaj hamshirasi",
  doctor: "Oilaviy shifokor",
  specialist: "OvaBMU mutaxassisi",
  department_head: "Bo'lim mudiri (OvaBMU)",
  district_admin: "Tuman tibbiyot birlashmasi",
  region_admin: "Viloyat sog'liqni saqlash boshqarmasi",
};

export const SYMPTOM_LABEL: Record<string, string> = {
  bleeding: "Qon ketishi",
  severe_headache: "Kuchli bosh og'rig'i",
  visual_disturbance: "Ko'rish buzilishi",
  epigastric_pain: "Epigastral og'riq",
  seizures: "Talvasa",
  dyspnea: "Hansirash",
  reduced_fetal_movement: "Homila harakati kamaygan",
  contractions: "To'lg'oq",
  membrane_rupture: "Suv ketishi",
  edema: "Shish",
};

export const PROTEINURIA_LABEL: Record<string, string> = {
  neg: "Manfiy", trace: "Iz", "+1": "+1", "+2": "+2", "+3": "+3",
};

export const ALERT_STATUS_LABEL: Record<string, string> = {
  open: "Ochiq",
  acknowledged: "Qabul qilingan",
  escalated: "Eskalatsiya",
  resolved: "Yopilgan",
};

export const ALERT_EVENT_LABEL: Record<string, string> = {
  created: "Ogohlantirish yaratildi",
  escalated: "Eskalatsiya: yuqori darajaga yuborildi",
  reassigned: "Qayta biriktirildi",
  acknowledged: "Qabul qilindi",
  resolved: "Yopildi",
  admin_notified: "Tuman boshqaruviga xabar berildi (faqat soni)",
};

export const SUBJECT_LABEL: Record<"pregnancy" | "child" | "all", string> = {
  pregnancy: "Homiladorlar",
  child: "Bolalar (0–1 yosh)",
  all: "Hammasi",
};

export const SEX_LABEL: Record<string, string> = { m: "O'g'il", f: "Qiz" };

export const FEEDING_LABEL: Record<string, string> = {
  exclusive_breast: "Faqat ko'krak suti",
  mixed: "Aralash",
  formula: "Sun'iy aralashma",
  complementary: "Qo'shimcha ovqat",
};

/** Infant danger signs / complaints entered in a child check (boolean fields). */
export const CHILD_SIGN_LABEL: Record<string, string> = {
  not_feeding_well: "Emmayapti / ovqatlana olmaydi",
  vomiting_everything: "Hamma narsani qayt qiladi",
  convulsions: "Talvasa",
  lethargic: "Holsiz / hushi xira",
  movement_only_when_stimulated: "Faqat qo'zg'atilganda harakatlanadi",
  severe_chest_indrawing: "Ko'krak qafasi kuchli tortiladi",
  blood_in_stool: "Najasda qon",
  jaundice_first_24h: "Sariqlik (birinchi 24 soatda)",
  jaundice_palms_soles: "Sariqlik kaft / tovonda",
};

export const VACCINE_STATUS_LABEL: Record<string, string> = {
  given: "Qilingan",
  overdue: "Kechikkan",
  due: "Muddati keldi",
  upcoming: "Rejada",
};

export const NO_ML_NOTE = "Bolalar uchun faqat klinik qoidalar va trendlar ishlatiladi (ML modeli qo'llanilmaydi).";

export const FINAL_DECISION = "Yakuniy qaror shifokorga tegishli";

export const DISCLAIMER =
  "Bu tizim qaror qabul qilishda yordam beradi, tashxis qo'ymaydi. Yakuniy qarorni shifokor qabul qiladi.";

export const DEMO_USERS: { polyclinic: string; username: string; role: Role; label: string }[] = [
  { polyclinic: "PL-NUK-001", username: "nurse", role: "nurse", label: "Hamshira (Nukus)" },
  { polyclinic: "PL-NUK-001", username: "doctor", role: "doctor", label: "Oilaviy shifokor (Nukus)" },
  { polyclinic: "PL-NUK-001", username: "specialist", role: "specialist", label: "OvaBMU mutaxassisi (Nukus)" },
  { polyclinic: "PL-NUK-001", username: "department_head", role: "department_head", label: "Bo'lim mudiri (Nukus)" },
  { polyclinic: "PL-SAM-003", username: "nurse", role: "nurse", label: "Hamshira (Samarqand · Registon)" },
  { polyclinic: "PL-SAM-003", username: "nurse2", role: "nurse", label: "Hamshira (Samarqand · Siyob)" },
  { polyclinic: "PL-SAM-003", username: "doctor", role: "doctor", label: "Oilaviy shifokor (Samarqand)" },
  { polyclinic: "PL-SAM-003", username: "specialist", role: "specialist", label: "OvaBMU mutaxassisi (Samarqand)" },
  { polyclinic: "PL-CHL-001", username: "nurse", role: "nurse", label: "Hamshira (Chilonzor)" },
  { polyclinic: "", username: "district.admin", role: "district_admin", label: "Tuman admini (Nukus)" },
  { polyclinic: "", username: "region.admin", role: "region_admin", label: "Viloyat admini (QQR)" },
  { polyclinic: "", username: "sam.district.admin", role: "district_admin", label: "Tuman admini (Samarqand)" },
  { polyclinic: "", username: "sam.region.admin", role: "region_admin", label: "Viloyat admini (Samarqand)" },
];

export const SATELLITE = {
  url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  attribution: "Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
};
export const STREETS = {
  url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
  attribution: "&copy; OpenStreetMap contributors",
};
