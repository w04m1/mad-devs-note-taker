import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { BellRing } from "lucide-react";
type Toast = { id: string; message: string };
const Context = createContext<{ show: (message: string) => void }>({
  show: () => undefined,
});
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const show = useCallback((message: string) => {
    const id = crypto.randomUUID();
    setToasts((value) => [...value, { id, message }]);
    window.setTimeout(
      () => setToasts((value) => value.filter((toast) => toast.id !== id)),
      5000,
    );
  }, []);
  const value = useMemo(() => ({ show }), [show]);
  return (
    <Context.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="fixed bottom-4 right-4 flex w-[min(24rem,calc(100%-2rem))] flex-col gap-2"
      >
        {toasts.map((toast) => (
          <div
            role="status"
            className="flex items-start gap-3 rounded-xl border bg-card p-4 text-sm shadow-xl"
            key={toast.id}
          >
            <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <BellRing />
            </span>
            <span className="pt-1.5">{toast.message}</span>
          </div>
        ))}
      </div>
    </Context.Provider>
  );
}
export const useToast = () => useContext(Context);
