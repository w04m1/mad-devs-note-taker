import { useState, type FormEvent } from "react";
import { DateTime } from "luxon";
import type { Note, NoteWrite, ReminderOffset, Tag } from "../../api/contracts";
import { api, ApiError } from "../../api/client";
import { useNoteMutations } from "../../api/mutations";
import { noteFormSchema } from "../../forms/schemas";
import { Button } from "../../components/ui/button";
import { Field, Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import { Checkbox } from "../../components/ui/checkbox";
import { Switch } from "../../components/ui/switch";
import { RadioGroup, RadioGroupItem } from "../../components/ui/radio-group";
import { DateTimePicker } from "../../components/date-time-picker";
import { AlertTriangle, Clock3, Save } from "lucide-react";

type Draft = {
  title: string;
  body: string;
  starts_at: string;
  active: boolean;
  tag_ids: string[];
  reminder_offsets_minutes: ReminderOffset[];
};
const localDate = (iso: string, timezone: string) =>
  DateTime.fromISO(iso, { setZone: true })
    .setZone(timezone)
    .toFormat("yyyy-LL-dd\'T\'HH:mm");
const initial = (timezone: string, note?: Note): Draft =>
  note
    ? {
        title: note.title,
        body: note.body,
        starts_at: localDate(note.starts_at, timezone),
        active: note.active,
        tag_ids: note.tags.map((t) => t.id),
        reminder_offsets_minutes: note.reminder_offsets_minutes,
      }
    : {
        title: "",
        body: "",
        starts_at: localDate(
          new Date(Date.now() + 3600000).toISOString(),
          timezone,
        ),
        active: true,
        tag_ids: [],
        reminder_offsets_minutes: [],
      };
export function manualNoteChoices(value: string, timezone: string): string[] {
  const local = DateTime.fromISO(value, { zone: timezone });
  if (!local.isValid || local.toFormat("yyyy-LL-dd'T'HH:mm") !== value)
    return [];
  return local
    .getPossibleOffsets()
    .sort((left, right) => left.toMillis() - right.toMillis())
    .map((candidate) => candidate.toISO())
    .filter(
      (candidate, index, all) =>
        candidate !== null && all.indexOf(candidate) === index,
    ) as string[];
}
export function manualNoteInstant(
  value: string,
  timezone: string,
  overlapChoice?: string | null,
): string | null {
  const candidates = manualNoteChoices(value, timezone);
  if (candidates.length === 0) return null;
  if (candidates.length === 1) return candidates[0]!;
  return overlapChoice && candidates.includes(overlapChoice)
    ? overlapChoice
    : null;
}
const offsetLabel = (candidate: string, index: number) => {
  const instant = DateTime.fromISO(candidate, { setZone: true });
  return `${index === 0 ? "First" : "Second"} occurrence — UTC${instant.toFormat("ZZ")} (${instant.toUTC().toFormat("HH:mm 'UTC'")})`;
};
function payload(draft: Draft, startsAt: string): NoteWrite {
  return { ...draft, starts_at: startsAt };
}
export function NoteForm({
  note,
  tags,
  timezone,
  onSaved,
  onCancel,
}: {
  note?: Note;
  tags: Tag[];
  timezone: string;
  onSaved: () => void;
  onCancel: () => void;
}) {
  // Deliberately initialize once. Query invalidation/realtime rerenders must not overwrite a dirty draft.
  const [draft, setDraft] = useState<Draft>(() => initial(timezone, note));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [overlapChoice, setOverlapChoice] = useState<string | null>(null);
  const overlapChoices = manualNoteChoices(draft.starts_at, timezone);
  const mutations = useNoteMutations();
  const mutation = note ? mutations.update : mutations.create;
  const [conflict, setConflict] = useState<unknown>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErrors({});
    setConflict(null);
    const startsAt = manualNoteInstant(
      draft.starts_at,
      timezone,
      overlapChoice,
    );
    if (startsAt === null) {
      setErrors({
        starts_at:
          overlapChoices.length > 1
            ? "Choose which occurrence of this local time to use."
            : "This local time does not exist in the selected timezone.",
      });
      return;
    }
    const parsed = noteFormSchema.safeParse(payload(draft, startsAt));
    if (!parsed.success) {
      setErrors(
        Object.fromEntries(
          parsed.error.issues.map((i) => [String(i.path[0]), i.message]),
        ),
      );
      return;
    }
    try {
      if (note) {
        const expected_series_version = note.series_id
          ? (await api.series.get(note.series_id)).version
          : undefined;
        await mutations.update.mutateAsync({
          id: note.id,
          value: {
            ...parsed.data,
            expected_version: note.version,
            ...(expected_series_version === undefined
              ? {}
              : { expected_series_version }),
          },
        });
      } else await mutations.create.mutateAsync(parsed.data);
      onSaved();
    } catch (error) {
      if (error instanceof ApiError && error.status === 409)
        setConflict(error.body.current);
      else
        setErrors({
          form: error instanceof Error ? error.message : "Save failed",
        });
    }
  };
  const toggleTag = (id: string) =>
    setDraft((d) => ({
      ...d,
      tag_ids: d.tag_ids.includes(id)
        ? d.tag_ids.filter((x) => x !== id)
        : [...d.tag_ids, id],
    }));
  const toggleReminder = (value: ReminderOffset) =>
    setDraft((d) => ({
      ...d,
      reminder_offsets_minutes: d.reminder_offsets_minutes.includes(value)
        ? d.reminder_offsets_minutes.filter((x) => x !== value)
        : [...d.reminder_offsets_minutes, value],
    }));
  return (
    <form
      className="flex flex-col gap-5"
      onSubmit={submit}
      aria-label={note ? "Edit note" : "Create note"}
    >
      {conflict !== null && (
        <div role="alert" className="rounded-xl border bg-muted p-4">
          <strong className="flex items-center gap-2">
            <AlertTriangle />
            This note changed elsewhere.
          </strong>
          <p className="mt-1 text-sm text-muted-foreground">
            Your draft is still here. Cancel and reopen to load the latest
            version, or copy your changes first.
          </p>
          <details>
            <summary className="mt-2 cursor-pointer text-sm font-medium">
              Latest server value
            </summary>
            <pre className="mt-2 overflow-auto rounded-lg bg-background p-3 text-xs">
              {JSON.stringify(conflict, null, 2)}
            </pre>
          </details>
        </div>
      )}
      {errors.form && (
        <p
          role="alert"
          className="rounded-lg bg-destructive/5 p-3 text-sm text-destructive"
        >
          {errors.form}
        </p>
      )}
      <Field label="Title" error={errors.title}>
        <Input
          value={draft.title}
          onChange={(e) => setDraft({ ...draft, title: e.target.value })}
        />
      </Field>
      <Field label="Body" error={errors.body}>
        <Textarea
          className="min-h-28 resize-y"
          value={draft.body}
          onChange={(e) => setDraft({ ...draft, body: e.target.value })}
        />
      </Field>
      <Field label="Date and time" error={errors.starts_at}>
        <DateTimePicker
          label="Date and time"
          value={draft.starts_at}
          onChange={(value) => {
            setDraft({ ...draft, starts_at: value });
            setOverlapChoice(null);
            setErrors((previous) => ({ ...previous, starts_at: "" }));
          }}
        />
      </Field>
      {overlapChoices.length > 1 && (
        <fieldset className="grid gap-2 rounded-xl border bg-muted p-4">
          <legend className="px-1 text-sm font-medium">
            This time occurs twice. Choose one.
          </legend>
          <p className="text-sm text-muted-foreground">
            Timezone: {timezone}. The UTC offsets lead to different reminder
            times.
          </p>
          <RadioGroup
            value={overlapChoice}
            aria-required="true"
            onValueChange={(candidate) => {
              setOverlapChoice(candidate);
              setErrors((previous) => ({ ...previous, starts_at: "" }));
            }}
            required
          >
            {overlapChoices.map((candidate, index) => (
              <label
                key={candidate}
                className="flex items-center gap-3 rounded-lg border bg-background p-3 text-sm shadow-sm"
              >
                <RadioGroupItem value={candidate} />
                {offsetLabel(candidate, index)}
              </label>
            ))}
          </RadioGroup>
        </fieldset>
      )}
      <label className="flex items-center justify-between rounded-xl border bg-muted/45 p-4">
        <span>
          <span className="block text-sm font-medium">Active note</span>
          <span className="block text-xs text-muted-foreground">
            Include this note in schedules and reminders.
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
          {tags.map((tag) => (
            <label
              key={tag.id}
              className="flex items-center gap-2 rounded-lg border bg-background px-3 py-2 text-sm shadow-sm"
            >
              <Checkbox
                checked={draft.tag_ids.includes(tag.id)}
                onCheckedChange={() => toggleTag(tag.id)}
              />
              <span
                className="size-3 rounded-full"
                style={{ backgroundColor: tag.color }}
              />
              {tag.name}
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
          ).map(([value, label]) => (
            <label
              key={value}
              className="flex items-center gap-2 rounded-lg border bg-background px-3 py-2 text-sm shadow-sm"
            >
              <Checkbox
                checked={draft.reminder_offsets_minutes.includes(value)}
                onCheckedChange={() => toggleReminder(value)}
              />
              <Clock3 aria-hidden />
              {label}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="flex flex-col-reverse gap-2 border-t pt-5 sm:flex-row sm:justify-end">
        <Button disabled={mutation.isPending}>
          {!mutation.isPending && <Save data-icon="inline-start" />}
          {mutation.isPending ? "Saving…" : "Save note"}
        </Button>
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
