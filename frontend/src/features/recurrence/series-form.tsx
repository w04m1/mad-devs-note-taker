import { useEffect, useState, type FormEvent } from "react";
import { DateTime } from "luxon";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../../api/client";
import { queryKeys } from "../../api/query-keys";
import type {
  Frequency,
  Note,
  RecurrenceSeries,
  ReminderOffset,
  Tag,
} from "../../api/contracts";
import { Button } from "../../components/ui/button";
import { Field, Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import { Checkbox } from "../../components/ui/checkbox";
import { Switch } from "../../components/ui/switch";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../components/ui/select";
import { AlertTriangle, Clock3, Save } from "lucide-react";
import { DateTimePicker } from "../../components/date-time-picker";

type Draft = {
  title: string;
  body: string;
  local_start: string;
  end_date: string;
  frequency: Frequency;
  active: boolean;
  tag_ids: string[];
  reminder_offsets_minutes: ReminderOffset[];
};
export function recurrenceStartInstant(
  value: string,
  timezone: string,
): string | null {
  const local = DateTime.fromISO(value, { zone: timezone });
  if (!local.isValid || local.toFormat("yyyy-LL-dd'T'HH:mm") !== value)
    return null;
  const candidates = local.getPossibleOffsets();
  const earliest = candidates.reduce(
    (first, candidate) =>
      candidate.toMillis() < first.toMillis() ? candidate : first,
    local,
  );
  return earliest.toUTC().toISO();
}
const defaults = (
  timezone: string,
  note?: Note,
  series?: RecurrenceSeries,
): Draft => {
  const local = note
    ? DateTime.fromISO(note.starts_at, { setZone: true }).setZone(timezone)
    : DateTime.now().setZone(timezone).plus({ hours: 1 });
  return {
    title: note?.title ?? "",
    body: note?.body ?? "",
    local_start: local.toFormat("yyyy-LL-dd'T'HH:mm"),
    end_date: series?.end_date ?? local.plus({ months: 1 }).toISODate()!,
    frequency: series?.frequency ?? "weekly",
    active: note?.active ?? true,
    tag_ids: note?.tags.map((t) => t.id) ?? [],
    reminder_offsets_minutes: note?.reminder_offsets_minutes ?? [],
  };
};
export function SeriesForm({
  timezone,
  tags,
  note,
  series,
  onSaved,
  onCancel,
}: {
  timezone: string;
  tags: Tag[];
  note?: Note;
  series?: RecurrenceSeries;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const scheduleZone = series?.timezone ?? timezone;
  const [draft, setDraft] = useState(() =>
    defaults(scheduleZone, note, series),
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const client = useQueryClient();
  const toggleTag = (id: string) =>
    setDraft((d) => ({
      ...d,
      tag_ids: d.tag_ids.includes(id)
        ? d.tag_ids.filter((x) => x !== id)
        : [...d.tag_ids, id],
    }));
  const toggleReminder = (n: ReminderOffset) =>
    setDraft((d) => ({
      ...d,
      reminder_offsets_minutes: d.reminder_offsets_minutes.includes(n)
        ? d.reminder_offsets_minutes.filter((x) => x !== n)
        : [...d.reminder_offsets_minutes, n],
    }));
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    const local = DateTime.fromISO(draft.local_start, { zone: scheduleZone });
    const startsAt = recurrenceStartInstant(draft.local_start, scheduleZone);
    if (!draft.title.trim()) {
      setError("Title is required.");
      return;
    }
    if (!startsAt) {
      setError(
        "That local date and time does not exist in the schedule timezone.",
      );
      return;
    }
    if (draft.end_date < local.toISODate()!) {
      setError("End date must be on or after the first occurrence.");
      return;
    }
    setBusy(true);
    const common = {
      ...draft,
      title: draft.title.trim(),
      starts_at: startsAt,
      timezone: scheduleZone,
    };
    try {
      if (note) {
        if (!note.series_id || !note.recurrence_key)
          throw new Error("Series context is missing.");
        const current = await api.series.get(note.series_id);
        await api.series.split(current.id, {
          ...common,
          recurrence_key: note.recurrence_key,
          expected_version: current.version,
          expected_occurrence_version: note.version,
        });
      } else await api.series.create(common);
      await Promise.all([
        client.invalidateQueries({ queryKey: queryKeys.series.all }),
        client.invalidateQueries({ queryKey: queryKeys.notes.all }),
        client.invalidateQueries({ queryKey: queryKeys.calendar.all }),
        client.invalidateQueries({ queryKey: queryKeys.upcoming.all }),
      ]);
      onSaved();
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 409
          ? "The series changed elsewhere. Your draft is preserved; cancel and reopen to reload it."
          : e instanceof Error
            ? e.message
            : "Series save failed",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <form
      aria-busy={busy}
      aria-label={
        note ? "Edit this and future occurrences" : "Create recurring series"
      }
      onSubmit={submit}
      className="flex flex-col gap-5"
    >
      {note && (
        <div role="alert" className="rounded-xl border bg-muted p-4">
          <strong className="flex items-center gap-2">
            <AlertTriangle />
            Future exceptions will be replaced.
          </strong>
          <p className="mt-1 text-sm text-muted-foreground">
            Individual edits, moved dates, and cancellations from this
            occurrence onward will be removed. Earlier history stays unchanged.
          </p>
        </div>
      )}
      {error && (
        <p
          role="alert"
          className="rounded-lg bg-destructive/5 p-3 text-sm text-destructive"
        >
          {error}
        </p>
      )}
      <Field label="Title">
        <Input
          value={draft.title}
          onChange={(e) => setDraft({ ...draft, title: e.target.value })}
        />
      </Field>
      <Field label="Body">
        <Textarea
          className="min-h-24 resize-y"
          value={draft.body}
          onChange={(e) => setDraft({ ...draft, body: e.target.value })}
        />
      </Field>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="First local date and time">
          <DateTimePicker
            label="First local date and time"
            value={draft.local_start}
            onChange={(value) =>
              setDraft({ ...draft, local_start: value })
            }
          />
        </Field>
        <Field label="Repeat">
          <Select
            value={draft.frequency}
            onValueChange={(value) =>
              setDraft({ ...draft, frequency: value as Frequency })
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="daily">Daily</SelectItem>
                <SelectItem value="weekly">Weekly</SelectItem>
                <SelectItem value="monthly">Monthly</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </Field>
        <Field label="Inclusive end date">
          <DateTimePicker
            label="Inclusive end date"
            mode="date"
            value={draft.end_date}
            onChange={(value) => setDraft({ ...draft, end_date: value })}
          />
        </Field>
      </div>
      <p className="rounded-lg bg-muted p-3 text-sm leading-relaxed text-muted-foreground">
        Schedule timezone: {scheduleZone}. Invalid monthly dates and nonexistent
        daylight-saving times are skipped.
      </p>
      <label className="flex items-center justify-between rounded-xl border bg-muted/45 p-4">
        <span>
          <span className="block text-sm font-medium">Active series</span>
          <span className="block text-xs text-muted-foreground">
            Show occurrences and schedule reminders.
          </span>
        </span>
        <Switch
          checked={draft.active}
          onCheckedChange={(checked) => setDraft({ ...draft, active: checked })}
        />
      </label>
      <fieldset className="flex flex-col gap-3">
        <legend className="text-sm font-medium">Tags</legend>
        <div className="flex flex-wrap gap-2">
          {tags.map((t) => (
            <label
              key={t.id}
              className="flex items-center gap-2 rounded-lg border bg-background px-3 py-2 text-sm shadow-sm"
            >
              <Checkbox
                checked={draft.tag_ids.includes(t.id)}
                onCheckedChange={() => toggleTag(t.id)}
              />
              <span
                className="size-2 rounded-full"
                style={{ backgroundColor: t.color }}
              />
              {t.name}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset className="flex flex-col gap-3">
        <legend className="text-sm font-medium">Reminders</legend>
        <div className="flex flex-wrap gap-2">
          {(
            [
              [10, "10 minutes"],
              [60, "1 hour"],
              [1440, "1 day"],
            ] as const
          ).map(([n, l]) => (
            <label
              key={n}
              className="flex items-center gap-2 rounded-lg border bg-background px-3 py-2 text-sm shadow-sm"
            >
              <Checkbox
                checked={draft.reminder_offsets_minutes.includes(n)}
                onCheckedChange={() => toggleReminder(n)}
              />
              <Clock3 aria-hidden />
              {l}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="flex flex-col-reverse gap-2 border-t pt-5 sm:flex-row sm:justify-end">
        <Button disabled={busy}>
          {!busy && <Save data-icon="inline-start" />}
          {busy ? "Saving…" : "Save series"}
        </Button>
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

export function RecurringEditChoice({
  note,
  timezone,
  tags,
  onClose,
}: {
  note: Note;
  timezone: string;
  tags: Tag[];
  onClose: () => void;
}) {
  const [scope, setScope] = useState<"choose" | "one" | "future">("choose");
  useEffect(() => setScope("choose"), [note.id]);
  if (scope === "one")
    return (
      <NoteForm
        note={note}
        timezone={timezone}
        tags={tags}
        onSaved={onClose}
        onCancel={onClose}
      />
    );
  if (scope === "future")
    return (
      <FutureSeriesForm
        note={note}
        timezone={timezone}
        tags={tags}
        onClose={onClose}
      />
    );
  return (
    <div className="grid gap-3">
      <h2 className="text-lg font-bold">Edit recurring note</h2>
      <p>Choose the scope of your changes.</p>
      <Button onClick={() => setScope("one")}>Only this occurrence</Button>
      <Button variant="outline" onClick={() => setScope("future")}>
        This and future occurrences
      </Button>
      <Button variant="outline" onClick={onClose}>
        Cancel
      </Button>
    </div>
  );
}
import { NoteForm } from "../notes/note-form";

function FutureSeriesForm({
  note,
  timezone,
  tags,
  onClose,
}: {
  note: Note;
  timezone: string;
  tags: Tag[];
  onClose: () => void;
}) {
  const query = useQuery({
    queryKey: [...queryKeys.series.all, note.series_id],
    queryFn: () => api.series.get(note.series_id!),
    enabled: !!note.series_id,
  });
  if (query.isPending) return <p role="status">Loading series…</p>;
  if (query.isError)
    return <p role="alert">Series details could not be loaded.</p>;
  return (
    <SeriesForm
      note={note}
      series={query.data}
      timezone={timezone}
      tags={tags}
      onSaved={onClose}
      onCancel={onClose}
    />
  );
}
