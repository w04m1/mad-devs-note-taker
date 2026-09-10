import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import FullCalendar from "@fullcalendar/react";
import type { EventDropArg } from "@fullcalendar/core";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import interactionPlugin from "@fullcalendar/interaction";
import luxonPlugin from "@fullcalendar/luxon3";
import { DateTime } from "luxon";
import { useSearchParams } from "react-router-dom";
import { api, ApiError } from "../../api/client";
import { queryKeys } from "../../api/query-keys";
import type { Note } from "../../api/contracts";
import { NoteForm } from "../notes/note-form";
import { RecurringEditChoice } from "../recurrence/series-form";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { AlertTriangle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "../../components/ui/dialog";

type View = "dayGridMonth" | "timeGridWeek" | "timeGridDay";
type Range = { starts_from: string; starts_to: string };
type PendingDrop = { info: EventDropArg; note: Note; startsAt: string };
const views = new Set<View>(["dayGridMonth", "timeGridWeek", "timeGridDay"]);

/** Preserve FullCalendar's offset-qualified named-zone result instead of reinterpreting it in the browser zone. */
export function droppedInstant(value: string, timezone: string): string {
  const result = DateTime.fromISO(value, { setZone: true }).setZone(timezone);
  if (!result.isValid)
    throw new Error("That local time does not exist in the selected timezone.");
  return result.toUTC().toISO()!;
}

export function CalendarView({
  timezone,
  tags,
}: {
  timezone: string;
  tags: Note["tags"];
}) {
  const [url, setUrl] = useSearchParams();
  const desiredView = views.has(url.get("view") as View)
    ? (url.get("view") as View)
    : "dayGridMonth";
  const desiredDate = DateTime.fromISO(url.get("date") ?? "", {
    zone: timezone,
  }).isValid
    ? url.get("date")!
    : DateTime.now().setZone(timezone).toISODate()!;
  const calendarRef = useRef<FullCalendar>(null);
  const [range, setRange] = useState<Range>();
  const [opened, setOpened] = useState<Note>();
  const [pending, setPending] = useState<PendingDrop>();
  const [error, setError] = useState<string>();
  const notesById = useRef(new Map<string, Note>());
  const client = useQueryClient();
  const query = useQuery({
    queryKey: [...queryKeys.calendar.all, range],
    queryFn: () => api.calendar(range!),
    enabled: !!range,
  });
  useEffect(() => {
    const calendar = calendarRef.current?.getApi();
    if (!calendar) return;
    if (calendar.view.type !== desiredView)
      calendar.changeView(desiredView, desiredDate);
    else {
      const visible = DateTime.fromJSDate(calendar.view.currentStart)
        .setZone(timezone)
        .toISODate();
      if (visible !== desiredDate) calendar.gotoDate(desiredDate);
    }
  }, [desiredDate, desiredView, timezone]);
  notesById.current = new Map(
    (query.data ?? []).map((note) => [note.id, note]),
  );
  const events = useMemo(
    () =>
      (query.data ?? []).map((note) => ({
        id: note.id,
        title: note.title,
        start: note.starts_at,
        allDay: false,
        extendedProps: { active: note.active },
      })),
    [query.data],
  );
  const invalidate = () =>
    Promise.all([
      client.invalidateQueries({ queryKey: queryKeys.calendar.all }),
      client.invalidateQueries({ queryKey: queryKeys.notes.all }),
      client.invalidateQueries({ queryKey: queryKeys.upcoming.all }),
    ]);
  const fail = (info: EventDropArg, e: unknown) => {
    info.revert();
    setError(
      e instanceof ApiError
        ? e.body.message
        : e instanceof Error
          ? e.message
          : "Move failed",
    );
    void invalidate();
  };
  const moveOne = async (p: PendingDrop) => {
    try {
      let seriesVersion: number | undefined;
      if (p.note.series_id)
        seriesVersion = (await api.series.get(p.note.series_id)).version;
      await api.notes.update(p.note.id, {
        title: p.note.title,
        body: p.note.body,
        starts_at: p.startsAt,
        active: p.note.active,
        tag_ids: p.note.tags.map((t) => t.id),
        reminder_offsets_minutes: p.note.reminder_offsets_minutes,
        expected_version: p.note.version,
        ...(seriesVersion === undefined
          ? {}
          : { expected_series_version: seriesVersion }),
      });
      setPending(undefined);
      await invalidate();
    } catch (e) {
      setPending(undefined);
      fail(p.info, e);
    }
  };
  const moveFuture = async (p: PendingDrop) => {
    try {
      if (!p.note.series_id || !p.note.recurrence_key)
        throw new Error("Series details are unavailable.");
      const series = await api.series.get(p.note.series_id);
      const local = DateTime.fromISO(p.startsAt, { setZone: true }).setZone(
        series.timezone,
      );
      await api.series.split(series.id, {
        title: p.note.title,
        body: p.note.body,
        starts_at: p.startsAt,
        active: p.note.active,
        tag_ids: p.note.tags.map((t) => t.id),
        reminder_offsets_minutes: p.note.reminder_offsets_minutes,
        local_start: local.toFormat("yyyy-LL-dd'T'HH:mm:ss"),
        timezone: series.timezone,
        frequency: series.frequency,
        end_date: series.end_date,
        recurrence_key: p.note.recurrence_key,
        expected_version: series.version,
        expected_occurrence_version: p.note.version,
      });
      setPending(undefined);
      await invalidate();
    } catch (e) {
      setPending(undefined);
      fail(p.info, e);
    }
  };
  const cancelDrop = (p: PendingDrop) => {
    p.info.revert();
    setPending(undefined);
    void invalidate();
  };
  const drop = (info: EventDropArg) => {
    setError(undefined);
    const note = notesById.current.get(info.event.id);
    if (!note || !info.event.start || !info.event.startStr) {
      info.revert();
      return;
    }
    try {
      const startsAt = droppedInstant(info.event.startStr, timezone);
      const p = { info, note, startsAt };
      if (note.series_id) setPending(p);
      else void moveOne(p);
    } catch (e) {
      fail(info, e);
    }
  };
  return (
    <div className="flex flex-col gap-4">
      {error && (
        <p
          role="alert"
          className="rounded-xl border border-destructive/20 bg-destructive/5 p-4 text-sm text-destructive"
        >
          {error}
        </p>
      )}
      {query.isError && (
        <p role="alert">
          {query.error instanceof ApiError
            ? query.error.body.message
            : "Calendar could not be loaded."}
        </p>
      )}
      <Card className="overflow-hidden shadow-sm" aria-busy={query.isFetching}>
        <CardContent className="p-3 sm:p-5">
          <FullCalendar
            ref={calendarRef}
            plugins={[
              dayGridPlugin,
              timeGridPlugin,
              interactionPlugin,
              luxonPlugin,
            ]}
            initialView={desiredView}
            initialDate={desiredDate}
            timeZone={timezone}
            events={events}
            editable
            eventDurationEditable={false}
            forceEventDuration={false}
            height="auto"
            headerToolbar={{
              left: "prev,next today",
              center: "title",
              right: "dayGridMonth,timeGridWeek,timeGridDay",
            }}
            datesSet={(arg) => {
              const duration = arg.end.getTime() - arg.start.getTime();
              if (duration > 93 * 86400000) {
                setError("Calendar range must be 93 days or less.");
                return;
              }
              setRange({ starts_from: arg.startStr, starts_to: arg.endStr });
              setUrl(
                (previous) => {
                  const next = new URLSearchParams(previous);
                  next.set("view", arg.view.type);
                  next.set(
                    "date",
                    DateTime.fromJSDate(arg.view.currentStart)
                      .setZone(timezone)
                      .toISODate()!,
                  );
                  return next;
                },
                { replace: true },
              );
            }}
            eventClick={(arg) => {
              const note = notesById.current.get(arg.event.id);
              if (note) setOpened(note);
            }}
            eventDrop={drop}
          />
        </CardContent>
      </Card>
      <Dialog
        open={!!opened}
        onOpenChange={(open) => {
          if (!open) setOpened(undefined);
        }}
      >
        <DialogContent>
          <DialogTitle>Edit note</DialogTitle>
          <DialogDescription>
            Changes use the displayed timezone: {timezone}.
          </DialogDescription>
          {opened &&
            (opened.series_id ? (
              <RecurringEditChoice
                note={opened}
                tags={tags}
                timezone={timezone}
                onClose={() => setOpened(undefined)}
              />
            ) : (
              <NoteForm
                note={opened}
                tags={tags}
                timezone={timezone}
                onSaved={() => setOpened(undefined)}
                onCancel={() => setOpened(undefined)}
              />
            ))}
        </DialogContent>
      </Dialog>
      <Dialog
        open={!!pending}
        onOpenChange={(open) => {
          if (!open && pending) cancelDrop(pending);
        }}
      >
        <DialogContent>
          <DialogTitle>Move recurring note</DialogTitle>
          <DialogDescription>
            Choose which occurrences to change.
          </DialogDescription>
          <div className="grid gap-3">
            <Button onClick={() => pending && void moveOne(pending)}>
              Only this occurrence
            </Button>
            <div className="rounded-xl border bg-muted p-4 text-sm">
              <strong className="flex items-center gap-2">
                <AlertTriangle />
                This and future occurrences
              </strong>
              <p className="mt-1 text-muted-foreground">
                Future individual edits, moves, and cancellations will be
                replaced. Earlier history stays unchanged.
              </p>
            </div>
            <Button onClick={() => pending && void moveFuture(pending)}>
              Replace this and future
            </Button>
            <Button
              variant="outline"
              onClick={() => pending && cancelDrop(pending)}
            >
              Cancel move
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
