import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { DateTime } from "luxon";
import { api } from "../../api/client";
import { queryKeys } from "../../api/query-keys";
import type { Note, UpcomingResponse } from "../../api/contracts";
import { ArrowUpRight, CalendarClock } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../components/ui/card";

export function nextUpcomingDelay(
  data: UpcomingResponse | undefined,
  timezone: string,
  nowMs = Date.now(),
): number {
  const serverMs = data?.server_now
    ? DateTime.fromISO(data.server_now, { setZone: true }).toMillis()
    : nowMs;
  const serverNow = DateTime.fromMillis(serverMs, { zone: timezone });
  const midnight = serverNow.plus({ days: 1 }).startOf("day").toMillis();
  const transition = data?.next_transition_at
    ? DateTime.fromISO(data.next_transition_at, { setZone: true }).toMillis()
    : Infinity;
  return Math.max(0, Math.min(midnight, transition) - serverMs);
}
export function useUpcomingRefresh(
  data: UpcomingResponse | undefined,
  timezone: string,
) {
  const client = useQueryClient();
  useEffect(() => {
    const refresh = () =>
      void client.invalidateQueries({ queryKey: queryKeys.upcoming.all });
    const delay = nextUpcomingDelay(data, timezone);
    const timer = window.setTimeout(refresh, Math.min(delay, 2_147_000_000));
    const fallback = window.setInterval(refresh, 60_000);
    const visible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", visible);
    return () => {
      clearTimeout(timer);
      clearInterval(fallback);
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [client, data?.next_transition_at, data?.server_now, timezone]);
}
const format = (iso: string, timezone: string) =>
  DateTime.fromISO(iso, { setZone: true })
    .setZone(timezone)
    .toLocaleString(DateTime.DATETIME_MED);
function Group({
  title,
  notes,
  timezone,
  onOpen,
}: {
  title: string;
  notes: Note[];
  timezone: string;
  onOpen: (note: Note) => void;
}) {
  return (
    <section
      aria-labelledby={`upcoming-${title.replaceAll(" ", "-")}`}
      className="flex flex-col gap-3"
    >
      <div className="flex items-center justify-between">
        <h2
          id={`upcoming-${title.replaceAll(" ", "-")}`}
          aria-label={`${title} (${notes.length})`}
          className="text-lg font-semibold tracking-tight"
        >
          {title}
        </h2>
        <Badge variant="secondary">{notes.length}</Badge>
      </div>
      {notes.length === 0 ? (
        <p className="rounded-xl border border-dashed bg-card p-5 text-sm text-muted-foreground">
          No notes in this section.
        </p>
      ) : (
        <ul className="grid gap-3">
          {notes.map((n) => (
            <li key={n.id}>
              <button
                className="group w-full rounded-xl border bg-card p-4 text-left shadow-sm transition-[border-color,box-shadow,transform] hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md"
                onClick={() => onOpen(n)}
              >
                <span className="flex items-start justify-between gap-3">
                  <strong className="line-clamp-2">{n.title}</strong>
                  <ArrowUpRight className="shrink-0 text-muted-foreground transition-colors group-hover:text-primary" />
                </span>
                <time
                  dateTime={n.starts_at}
                  className="mt-2 flex items-center gap-2 text-sm text-muted-foreground"
                >
                  <CalendarClock aria-hidden />
                  {format(n.starts_at, timezone)}
                </time>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
export function UpcomingView({
  timezone,
  onOpen,
}: {
  timezone: string;
  onOpen: (note: Note) => void;
}) {
  const query = useQuery({
    queryKey: queryKeys.upcoming.all,
    queryFn: api.upcoming,
  });
  useUpcomingRefresh(query.data, timezone);
  if (query.isPending) return <p role="status">Loading upcoming notes…</p>;
  if (query.isError)
    return <p role="alert">Upcoming notes could not be loaded.</p>;
  return (
    <div
      className="grid gap-6 xl:grid-cols-3"
      aria-live="polite"
      aria-busy={query.isFetching}
    >
      <Group
        title="Today"
        notes={query.data.today.items}
        timezone={timezone}
        onOpen={onOpen}
      />
      <Group
        title="This week"
        notes={query.data.week.items}
        timezone={timezone}
        onOpen={onOpen}
      />
      <Group
        title="Past active"
        notes={query.data.past.items}
        timezone={timezone}
        onOpen={onOpen}
      />
    </div>
  );
}
