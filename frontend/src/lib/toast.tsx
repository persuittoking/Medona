import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

type Kind = "success" | "error" | "info" | "red";
interface Toast { id: number; kind: Kind; title: string; body?: string }

const Ctx = createContext<(t: Omit<Toast, "id">) => void>(() => {});

const STYLE: Record<Kind, string> = {
  success: "border-zgreen bg-green-50",
  error: "border-zred bg-red-50",
  info: "border-brand-600 bg-brand-50",
  red: "border-zred bg-red-600 text-white",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = Date.now() + Math.random();
    setToasts((x) => [...x, { ...t, id }]);
    setTimeout(() => setToasts((x) => x.filter((y) => y.id !== id)), 6000);
  }, []);
  return (
    <Ctx.Provider value={push}>
      {children}
      <div className="fixed bottom-4 right-4 z-[2000] flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`rounded-lg border-l-4 p-3 shadow-lg ${STYLE[t.kind]}`}>
            <div className="font-semibold">{t.title}</div>
            {t.body && <div className="mt-0.5 text-sm opacity-90">{t.body}</div>}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx);
