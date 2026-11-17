// All user-facing labels (Uzbek, Latin script).
import type { Role, Zone } from "../api/types";

export const ZONE_LABEL: Record<Zone, string> = { red: "Qizil", yellow: "Sariq", green: "Yashil" };
export const ZONE_COLOR: Record<Zone, string> = { red: "#DC2626", yellow: "#F59E0B", green: "#16A34A" };

export const ROLE_LABEL: Record<Role, string> = {
  nurse: "Patronaj hamshirasi",
  doctor: "Oilaviy shifokor",
  specialist: "OvaBMU mutaxassisi",
  admin: "Viloyat boshqarmasi",
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

export const DEMO_USERS: { username: string; role: Role; label: string }[] = [
  { username: "nurse.nukus", role: "nurse", label: "Hamshira (Nukus)" },
  { username: "doctor.nukus", role: "doctor", label: "Shifokor (Nukus)" },
  { username: "specialist.nukus", role: "specialist", label: "OvaBMU mutaxassisi (Nukus)" },
  { username: "admin.qoraqalpogiston", role: "admin", label: "Viloyat admini (Qoraqalpog'iston)" },
  { username: "nurse.chilonzor", role: "nurse", label: "Hamshira (Chilonzor)" },
  { username: "admin.toshkent", role: "admin", label: "Admin (Toshkent shahri)" },
];
