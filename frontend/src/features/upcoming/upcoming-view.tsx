import { useEffect, useState } from "react";
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
  total,
  timezone,
  onOpen,
}: {
  title: string;
  notes: Note[];
  total: number;
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
          aria-label={`${title} (${total})`}
          className="text-lg font-semibold tracking-tight"
        >
          {title}
        </h2>
        <Badge variant="secondary">{total}</Badge>
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
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: [...queryKeys.upcoming.all, page],
    queryFn: () => api.upcoming(page, 50),
  });
  useUpcomingRefresh(query.data, timezone);
  if (query.isPending) return <p role="status">Loading upcoming notes…</p>;
  if (query.isError)
    return <p role="alert">Upcoming notes could not be loaded.</p>;
  const maximumTotal = Math.max(
    query.data.today.total,
    query.data.week.total,
    query.data.past.total,
  );
  const pages = Math.max(1, Math.ceil(maximumTotal / 50));
  return (
    <div aria-live="polite" aria-busy={query.isFetching} className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-3">
        <Group title="Today" notes={query.data.today.items} total={query.data.today.total} timezone={timezone} onOpen={onOpen} />
        <Group title="This week" notes={query.data.week.items} total={query.data.week.total} timezone={timezone} onOpen={onOpen} />
        <Group title="Past active" notes={query.data.past.items} total={query.data.past.total} timezone={timezone} onOpen={onOpen} />
      </div>
      <nav aria-label="Upcoming pages" className="flex items-center justify-center gap-3">
        <button className="rounded-md border px-3 py-2 text-sm disabled:opacity-50" disabled={page === 1} onClick={() => setPage((value) => value - 1)}>Previous</button>
        <span className="text-sm text-muted-foreground">Page {page} of {pages}</span>
        <button className="rounded-md border px-3 py-2 text-sm disabled:opacity-50" disabled={page >= pages} onClick={() => setPage((value) => value + 1)}>Next</button>
      </nav>
    </div>
  );
}
