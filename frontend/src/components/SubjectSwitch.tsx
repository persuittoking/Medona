import type { Subject, SubjectCounts } from "../api/types";
import { SUBJECT_LABEL } from "../i18n/uz";

const ORDER: Subject[] = ["pregnancy", "child", "all"];

/** Segmented switch "Homiladorlar | Bolalar (0–1 yosh) | Hammasi" with a count on each segment. */
export function SubjectSwitch({ value, onChange, counts }: {
  value: Subject;
  onChange: (s: Subject) => void;
  counts?: Partial<SubjectCounts> | null;
}) {
  return (
    <div role="radiogroup" aria-label="Kimlar ko'rsatilsin"
      className="inline-flex max-w-full overflow-x-auto rounded-lg bg-slate-100 p-1 text-sm ring-1 ring-slate-200">
      {ORDER.map((s) => {
        const on = value === s;
        const n = counts?.[s];
        return (
          <button key={s} type="button" role="radio" aria-checked={on} onClick={() => onChange(s)}
            className={`flex items-center gap-1.5 whitespace-nowrap rounded-md px-3 py-1.5 font-medium transition ${on ? "bg-white text-brand-800 shadow-sm ring-1 ring-slate-200" : "text-slate-600 hover:text-slate-900"}`}>
            {s === "child" && <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-[3px] border-2 border-current" />}
            {s === "pregnancy" && <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-full border-2 border-current" />}
            {SUBJECT_LABEL[s]}
            {n != null && <span className={`rounded-full px-1.5 text-xs tabular-nums ${on ? "bg-brand-50 text-brand-800" : "bg-slate-200 text-slate-600"}`}>{n}</span>}
          </button>
        );
      })}
    </div>
  );
}
