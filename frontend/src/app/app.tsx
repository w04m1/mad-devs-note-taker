import { NavLink, Route, Routes } from "react-router-dom";
import {
  Bell,
  CalendarDays,
  FileText,
  Settings,
  Tags,
  Trash2,
  Clock3,
  Sparkles,
} from "lucide-react";
import {
  CalendarScreen,
  NotesScreen,
  NotificationsScreen,
  NotFoundScreen,
  SettingsScreen,
  TagsScreen,
  TrashScreen,
  UpcomingScreen,
} from "./screens";
import { useRealtime } from "../realtime/use-realtime";
import { useToast } from "../components/toast";
import { cn } from "../lib/utils";
import { ScreenErrorBoundary } from "./error-boundary";

const links = [
  { to: "/calendar", label: "Calendar", icon: CalendarDays },
  { to: "/notes", label: "Notes", icon: FileText },
  { to: "/upcoming", label: "Upcoming", icon: Clock3 },
  { to: "/trash", label: "Trash", icon: Trash2 },
  { to: "/tags", label: "Tags", icon: Tags },
  { to: "/notifications", label: "Notifications", icon: Bell },
  { to: "/settings", label: "Settings", icon: Settings },
];
export function App() {
  const { show } = useToast();
  useRealtime(show);
  return (
    <div className="min-h-screen bg-background lg:grid lg:grid-cols-[17rem_minmax(0,1fr)]">
      <aside className="border-b bg-card lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col lg:border-b-0 lg:border-r">
        <div className="flex h-16 items-center gap-3 border-b px-5 lg:h-20">
          <span className="flex size-10 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
            <Sparkles aria-hidden />
          </span>
          <div className="min-w-0">
            <a href="/calendar" className="block font-semibold tracking-tight">
              Notetaker
            </a>
            <p className="text-xs text-muted-foreground">Your day, in focus</p>
          </div>
        </div>
        <nav
          aria-label="Main navigation"
          className="flex gap-1 overflow-x-auto p-2 lg:flex-1 lg:flex-col lg:p-4"
        >
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex h-10 shrink-0 items-center gap-3 rounded-lg px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground",
                  isActive &&
                    "bg-primary text-primary-foreground shadow-sm hover:bg-primary hover:text-primary-foreground",
                )
              }
            >
              <Icon aria-hidden />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="hidden border-t p-4 lg:block">
          <p className="rounded-xl bg-muted p-3 text-xs leading-relaxed text-muted-foreground">
            Changes sync automatically across your open sessions.
          </p>
        </div>
      </aside>
      <main className="min-w-0 px-4 py-6 sm:px-6 lg:px-10 lg:py-9 xl:px-14">
        <div className="mx-auto max-w-[92rem]">
          <ScreenErrorBoundary>
            <Routes>
              <Route path="/" element={<CalendarScreen />} />
              <Route path="/calendar" element={<CalendarScreen />} />
              <Route path="/notes" element={<NotesScreen />} />
              <Route path="/upcoming" element={<UpcomingScreen />} />
              <Route path="/trash" element={<TrashScreen />} />
              <Route path="/tags" element={<TagsScreen />} />
              <Route path="/notifications" element={<NotificationsScreen />} />
              <Route path="/settings" element={<SettingsScreen />} />
              <Route path="*" element={<NotFoundScreen />} />
            </Routes>
          </ScreenErrorBoundary>
        </div>
      </main>
    </div>
  );
}
