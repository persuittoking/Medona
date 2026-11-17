// All user-facing labels (Uzbek, Latin script).
import type { Role, Zone } from "../api/types";

export const ZONE_LABEL: Record<Zone, string> = { red: "Qizil", yellow: "Sariq", green: "Yashil" };
export const ZONE_COLOR: Record<Zone, string> = { red: "#DC2626", yellow: "#F59E0B", green: "#16A34A" };

export const ROLE_LABEL: Record<Role, string> = {
  nurse: "Patronaj hamshirasi",
  doctor: "Oilaviy shifokor",
  specialist: "OvaBMU mutaxassisi",
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

export const DISCLAIMER =
  "Bu tizim qaror qabul qilishda yordam beradi, tashxis qo'ymaydi. Yakuniy qarorni shifokor qabul qiladi.";

export const DEMO_USERS: { polyclinic: string; username: string; role: Role; label: string }[] = [
  { polyclinic: "PL-NUK-001", username: "nurse", role: "nurse", label: "Hamshira" },
  { polyclinic: "PL-NUK-001", username: "doctor", role: "doctor", label: "Oilaviy shifokor" },
  { polyclinic: "PL-NUK-001", username: "specialist", role: "specialist", label: "OvaBMU mutaxassisi" },
  { polyclinic: "PL-CHL-001", username: "nurse", role: "nurse", label: "Hamshira (Chilonzor)" },
  { polyclinic: "", username: "district.admin", role: "district_admin", label: "Tuman admini" },
  { polyclinic: "", username: "region.admin", role: "region_admin", label: "Viloyat admini" },
];

export const SATELLITE = {
  url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  attribution: "Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
};
export const STREETS = {
  url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
  attribution: "&copy; OpenStreetMap contributors",
};
