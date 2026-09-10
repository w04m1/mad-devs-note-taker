import { lazy, Suspense, useEffect, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { DateTime } from "luxon";
import {
  ArchiveRestore,
  Bell,
  ChevronLeft,
  ChevronRight,
  FilePlus2,
  Pencil,
  Plus,
  Repeat2,
  Search,
  Tag as TagIcon,
  Trash2,
} from "lucide-react";
import { api, ApiError } from "../api/client";
import type {
  Direction,
  Note,
  NoteListParams,
  SortField,
  Tag,
} from "../api/contracts";
import { queryKeys } from "../api/query-keys";
import {
  useNoteMutations,
  useSettingsMutation,
  useTagMutations,
} from "../api/mutations";
import { Button } from "../components/ui/button";
import { Field, Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "../components/ui/card";
import { Checkbox } from "../components/ui/checkbox";
import {
  Empty as EmptyPrimitive,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "../components/ui/empty";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Skeleton } from "../components/ui/skeleton";
import { NoteForm } from "../features/notes/note-form";
import {
  searchSchema,
  settingsFormSchema,
  tagFormSchema,
} from "../forms/schemas";
import { UpcomingView } from "../features/upcoming/upcoming-view";
import {
  SeriesForm,
  RecurringEditChoice,
} from "../features/recurrence/series-form";
import {
  parseNoteParams,
  serializeNoteParams,
} from "../features/notes/note-filter-params";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import { DateTimePicker } from "../components/date-time-picker";

const CalendarView = lazy(async () => {
  const module = await import("../features/calendar/calendar-view");
  return { default: module.CalendarView };
});

function Screen({
  title,
  description,
  action,
  children,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
          <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted-foreground">
            {description}
          </p>
        </div>
        {action}
      </header>
      {children ?? (
        <Empty label="This workspace is ready for feature integration." />
      )}
    </section>
  );
}
const ErrorMessage = ({
  error,
  label = "Request failed.",
}: {
  error: unknown;
  label?: string;
}) => (
  <p
    role="alert"
    className="rounded-xl border border-destructive/20 bg-destructive/5 p-4 text-sm text-destructive"
  >
    {error instanceof ApiError ? error.body.message : label}
  </p>
);

function ConfirmAction({
  title,
  description,
  label,
  onConfirm,
  destructive = false,
}: {
  title: string;
  description: string;
  label: string;
  onConfirm: () => void;
  destructive?: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button
        type="button"
        variant={destructive ? "ghost" : "outline"}
        size="sm"
        onClick={() => setOpen(true)}
      >
        {destructive && <Trash2 data-icon="inline-start" />}
        {label}
      </Button>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => setOpen(false)}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant={destructive ? "destructive" : "default"}
            onClick={() => {
              setOpen(false);
              onConfirm();
            }}
          >
            {label}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
export function CalendarScreen() {
  const settings = useQuery({
    queryKey: queryKeys.settings.all,
    queryFn: api.settings.get,
  });
  const tags = useQuery({
    queryKey: queryKeys.tags.all,
    queryFn: api.tags.list,
  });
  return (
    <Screen title="Calendar" description="Month, week, and day schedule views.">
      {settings.isPending ? (
        <Loading label="Loading calendar…" />
      ) : settings.isError ? (
        <ErrorMessage error={settings.error} />
      ) : (
        <Suspense fallback={<Loading label="Loading calendar…" />}>
          <CalendarView
            timezone={settings.data.timezone}
            tags={tags.data ?? []}
          />
        </Suspense>
      )}
    </Screen>
  );
}

export function NotesScreen() {
  const [url, setUrl] = useSearchParams();
  const params = parseNoteParams(url);
  const [search, setSearch] = useState(params.q ?? "");
  const [searchError, setSearchError] = useState("");
  const [editing, setEditing] = useState<Note | "new" | "series" | null>(null);
  useEffect(() => setSearch(params.q ?? ""), [params.q]);
  useEffect(() => {
    const result = searchSchema.safeParse(search);
    if (!result.success) {
      setSearchError(result.error.issues[0]?.message ?? "Invalid search");
      return;
    }
    setSearchError("");
    const timer = window.setTimeout(
      () =>
        setUrl(
          (previous) => {
            const latest = parseNoteParams(previous);
            const next = { ...latest, page: 1 };
            if (result.data) next.q = result.data;
            else delete next.q;
            return next.q === (latest.q ?? undefined)
              ? previous
              : serializeNoteParams(next);
          },
          { replace: true },
        ),
      300,
    );
    return () => clearTimeout(timer);
  }, [search]);
  const query = useQuery({
    queryKey: queryKeys.notes.list(params),
    queryFn: ({ signal }) => api.notes.list(params, signal),
    placeholderData: (previous) => previous,
  });
  const settings = useQuery({
    queryKey: queryKeys.settings.all,
    queryFn: api.settings.get,
  });
  const tags = useQuery({
    queryKey: queryKeys.tags.all,
    queryFn: api.tags.list,
  });
  const set = <K extends keyof NoteListParams>(
    key: K,
    value: NoteListParams[K],
  ) => {
    const next = {
      ...params,
      [key]: value,
      page: key === "page" ? Number(value) : 1,
    };
    if (value === undefined) delete next[key];
    setUrl(serializeNoteParams(next));
  };
  const zone =
    settings.data?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone;
  const local = (iso?: string) =>
    iso
      ? DateTime.fromISO(iso, { setZone: true })
          .setZone(zone)
          .toFormat("yyyy-LL-dd'T'HH:mm")
      : "";
  const instant = (value: string) =>
    value
      ? (DateTime.fromISO(value, { zone }).toUTC().toISO() ?? undefined)
      : undefined;
  return (
    <Screen
      title="Notes"
      description="Search, filter, sort, and edit notes."
      action={
        <div className="flex gap-2">
          <Button onClick={() => setEditing("new")}>
            <Plus data-icon="inline-start" />
            New note
          </Button>
          <Button variant="outline" onClick={() => setEditing("series")}>
            <Repeat2 data-icon="inline-start" />
            New series
          </Button>
        </div>
      }
    >
      <Dialog
        open={!!editing}
        onOpenChange={(open) => {
          if (!open) setEditing(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editing === "series"
                ? "New recurring series"
                : editing === "new"
                  ? "New note"
                  : "Edit note"}
            </DialogTitle>
            <DialogDescription>
              Keep the details clear and choose when this belongs in your day.
            </DialogDescription>
          </DialogHeader>
          {editing &&
            (editing === "series" ? (
              <SeriesForm
                tags={tags.data ?? []}
                timezone={zone}
                onSaved={() => setEditing(null)}
                onCancel={() => setEditing(null)}
              />
            ) : editing === "new" ? (
              <NoteForm
                tags={tags.data ?? []}
                timezone={zone}
                onSaved={() => setEditing(null)}
                onCancel={() => setEditing(null)}
              />
            ) : editing.series_id ? (
              <RecurringEditChoice
                note={editing}
                tags={tags.data ?? []}
                timezone={zone}
                onClose={() => setEditing(null)}
              />
            ) : (
              <NoteForm
                note={editing}
                tags={tags.data ?? []}
                timezone={zone}
                onSaved={() => setEditing(null)}
                onCancel={() => setEditing(null)}
              />
            ))}
        </DialogContent>
      </Dialog>
      <form
        className="grid gap-4 rounded-2xl border bg-card p-5 shadow-sm lg:grid-cols-6"
        onSubmit={(e) => e.preventDefault()}
        aria-label="Note filters"
      >
        <div className="lg:col-span-2">
          <Field label="Search title and body" error={searchError}>
            <div className="relative">
              <Search
                aria-hidden
                className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              />
              <Input
                className="pl-9"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="At least 3 characters"
              />
            </div>
          </Field>
        </div>
        <Field label="Status">
          <Select
            value={params.active === undefined ? "all" : String(params.active)}
            onValueChange={(value) =>
              set("active", value === "all" ? undefined : value === "true")
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="all">All notes</SelectItem>
                <SelectItem value="true">Active</SelectItem>
                <SelectItem value="false">Inactive</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </Field>
        <fieldset className="flex flex-col gap-2 lg:col-span-2">
          <legend className="text-sm font-medium">Tags · all must match</legend>
          <div className="flex min-h-10 flex-wrap items-center gap-2 rounded-lg border bg-background px-3 py-2">
            {tags.data?.length ? (
              tags.data.map((tag) => (
                <label key={tag.id} className="flex items-center gap-2 text-xs">
                  <Checkbox
                    checked={(params.tag_id ?? []).includes(tag.id)}
                    onCheckedChange={() => {
                      const current = params.tag_id ?? [];
                      set(
                        "tag_id",
                        current.includes(tag.id)
                          ? current.filter((id) => id !== tag.id)
                          : [...current, tag.id],
                      );
                    }}
                  />
                  <span
                    className="size-2 rounded-full"
                    style={{ backgroundColor: tag.color }}
                  />
                  {tag.name}
                </label>
              ))
            ) : (
              <span className="text-xs text-muted-foreground">No tags</span>
            )}
          </div>
        </fieldset>
        <Field label="From">
          <DateTimePicker
            label="From"
            clearable
            defaultTime="00:00"
            value={local(params.starts_from)}
            onChange={(value) => set("starts_from", instant(value))}
          />
        </Field>
        <Field label="To">
          <DateTimePicker
            label="To"
            clearable
            defaultTime="23:59"
            value={local(params.starts_to)}
            onChange={(value) => set("starts_to", instant(value))}
          />
        </Field>
        <Field label="Sort">
          <Select
            value={params.sort ?? "starts_at"}
            onValueChange={(value) => set("sort", value as SortField)}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="starts_at">Note time</SelectItem>
                <SelectItem value="updated_at">Modified</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </Field>
        <Field label="Direction">
          <Select
            value={params.direction ?? "asc"}
            onValueChange={(value) => set("direction", value as Direction)}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="asc">Oldest first</SelectItem>
                <SelectItem value="desc">Newest first</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </Field>
      </form>
      {query.isPending ? (
        <Loading label="Loading notes…" />
      ) : query.isError ? (
        <ErrorMessage error={query.error} label="Notes could not be loaded." />
      ) : query.data.items.length === 0 ? (
        <Empty label="No matching notes." />
      ) : (
        <>
          <NoteCards
            notes={query.data.items}
            timezone={settings.data?.timezone}
            onEdit={setEditing}
          />
          <Pagination
            page={query.data.page}
            pageSize={query.data.page_size}
            total={query.data.total}
            onPage={(page) => set("page", page)}
          />
        </>
      )}
    </Screen>
  );
}
function NoteCards({
  notes,
  timezone,
  onEdit,
}: {
  notes: Note[];
  timezone?: string | undefined;
  onEdit: (note: Note) => void;
}) {
  const { update, remove } = useNoteMutations();
  const [error, setError] = useState<unknown>();
  const seriesVersion = async (note: Note) =>
    note.series_id ? (await api.series.get(note.series_id)).version : undefined;
  const act = async (note: Note) => {
    setError(undefined);
    try {
      const expected_series_version = await seriesVersion(note);
      await update.mutateAsync({
        id: note.id,
        value: {
          title: note.title,
          body: note.body,
          starts_at: note.starts_at,
          active: !note.active,
          tag_ids: note.tags.map((t) => t.id),
          reminder_offsets_minutes: note.reminder_offsets_minutes,
          expected_version: note.version,
          ...(expected_series_version === undefined
            ? {}
            : { expected_series_version }),
        },
      });
    } catch (e) {
      setError(e);
    }
  };
  return (
    <>
      {error && <ErrorMessage error={error} />}
      <ul className="grid gap-3">
        {notes.map((note) => (
          <li key={note.id}>
            <Card className="overflow-hidden shadow-sm transition-shadow hover:shadow-md">
              <CardHeader className="flex-row items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <Badge variant={note.active ? "default" : "secondary"}>
                      {note.active ? "Active" : "Inactive"}
                    </Badge>
                    {note.series_id && (
                      <Badge variant="outline">
                        <Repeat2 />
                        Recurring
                      </Badge>
                    )}
                  </div>
                  <CardTitle>
                    <h2 className="text-lg">{note.title}</h2>
                  </CardTitle>
                  <CardDescription>
                    <time dateTime={note.starts_at}>
                      {new Date(note.starts_at).toLocaleString(
                        undefined,
                        timezone ? { timeZone: timezone } : undefined,
                      )}
                    </time>
                  </CardDescription>
                </div>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                {note.body && (
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">
                    {note.body}
                  </p>
                )}
                <div className="flex flex-wrap gap-1.5">
                  {note.tags.map((t) => (
                    <Badge key={t.id} variant="outline">
                      <span
                        className="size-2 rounded-full"
                        style={{ backgroundColor: t.color }}
                      />
                      {t.name}
                    </Badge>
                  ))}
                </div>
              </CardContent>
              <CardFooter className="flex flex-wrap gap-2 border-t bg-muted/35 pt-4">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onEdit(note)}
                >
                  <Pencil data-icon="inline-start" />
                  Edit
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => void act(note)}
                >
                  {note.active ? "Deactivate" : "Activate"}
                </Button>
                <ConfirmAction
                  destructive
                  label="Move to trash"
                  title={`Move ${note.title} to trash?`}
                  description="You can restore this note from Trash for 30 days."
                  onConfirm={() => {
                    void seriesVersion(note)
                      .then((seriesVersion) =>
                        remove.mutateAsync({
                          id: note.id,
                          version: note.version,
                          ...(seriesVersion === undefined
                            ? {}
                            : { seriesVersion }),
                        }),
                      )
                      .catch(setError);
                  }}
                />
              </CardFooter>
            </Card>
          </li>
        ))}
      </ul>
    </>
  );
}
function Pagination({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <nav
      aria-label="Pagination"
      className="mt-2 flex items-center justify-between rounded-xl border bg-card p-2 shadow-sm"
    >
      <Button
        variant="outline"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
      >
        <ChevronLeft data-icon="inline-start" />
        Previous
      </Button>
      <span className="px-2 text-center text-sm text-muted-foreground">
        Page {page} of {pages} · {total} results
      </span>
      <Button
        variant="outline"
        disabled={page >= pages}
        onClick={() => onPage(page + 1)}
      >
        Next
        <ChevronRight data-icon="inline-end" />
      </Button>
    </nav>
  );
}
export function UpcomingScreen() {
  const settings = useQuery({
    queryKey: queryKeys.settings.all,
    queryFn: api.settings.get,
  });
  const tags = useQuery({
    queryKey: queryKeys.tags.all,
    queryFn: api.tags.list,
  });
  const [opened, setOpened] = useState<Note>();
  const zone =
    settings.data?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone;
  return (
    <Screen
      title="Upcoming"
      description="Today, this week, and past active notes."
    >
      <UpcomingView timezone={zone} onOpen={setOpened} />
      <Dialog
        open={!!opened}
        onOpenChange={(open) => {
          if (!open) setOpened(undefined);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit note</DialogTitle>
            <DialogDescription>
              Choose an edit scope for recurring notes.
            </DialogDescription>
          </DialogHeader>
          {opened &&
            (opened.series_id ? (
              <RecurringEditChoice
                note={opened}
                timezone={zone}
                tags={tags.data ?? []}
                onClose={() => setOpened(undefined)}
              />
            ) : (
              <NoteForm
                note={opened}
                timezone={zone}
                tags={tags.data ?? []}
                onSaved={() => setOpened(undefined)}
                onCancel={() => setOpened(undefined)}
              />
            ))}
        </DialogContent>
      </Dialog>
    </Screen>
  );
}

export function TrashScreen() {
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: [...queryKeys.trash.all, page],
    queryFn: () => api.notes.list({ trash: true, page, page_size: 20 }),
  });
  const { restore } = useNoteMutations();
  const [error, setError] = useState<unknown>();
  return (
    <Screen
      title="Trash"
      description="Restore notes before permanent removal after 30 days."
    >
      {error !== undefined && <ErrorMessage error={error} />}{" "}
      {query.isPending ? (
        <Loading label="Loading trash…" />
      ) : query.isError ? (
        <ErrorMessage error={query.error} />
      ) : query.data.items.length === 0 ? (
        <Empty label="Trash is empty." />
      ) : (
        <>
          <ul className="grid gap-3 lg:grid-cols-2">
            {query.data.items.map((note) => (
              <li
                className="flex items-center justify-between gap-4 rounded-xl border bg-card p-5 shadow-sm"
                key={note.id}
              >
                <div>
                  <strong>{note.title}</strong>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Deleted{" "}
                    {note.deleted_at
                      ? new Date(note.deleted_at).toLocaleString()
                      : "recently"}
                  </p>
                </div>
                <Button
                  size="sm"
                  onClick={() =>
                    void (
                      note.series_id
                        ? api.series.get(note.series_id).then((series) =>
                            restore.mutateAsync({
                              id: note.id,
                              version: note.version,
                              seriesVersion: series.version,
                            }),
                          )
                        : restore.mutateAsync({
                            id: note.id,
                            version: note.version,
                          })
                    ).catch(setError)
                  }
                >
                  <ArchiveRestore data-icon="inline-start" />
                  Restore
                </Button>
              </li>
            ))}
          </ul>
          <Pagination
            page={query.data.page}
            pageSize={query.data.page_size}
            total={query.data.total}
            onPage={setPage}
          />
        </>
      )}
    </Screen>
  );
}

export function TagsScreen() {
  const query = useQuery({
    queryKey: queryKeys.tags.all,
    queryFn: api.tags.list,
  });
  const mutations = useTagMutations();
  const [editing, setEditing] = useState<Tag>();
  const [name, setName] = useState("");
  const [color, setColor] = useState("#2563eb");
  const [error, setError] = useState("");
  const reset = () => {
    setEditing(undefined);
    setName("");
    setColor("#2563eb");
  };
  const edit = (tag: Tag) => {
    setEditing(tag);
    setName(tag.name);
    setColor(tag.color);
  };
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const parsed = tagFormSchema.safeParse({ name, color });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Invalid tag");
      return;
    }
    setError("");
    try {
      if (editing)
        await mutations.update.mutateAsync({
          id: editing.id,
          value: { ...parsed.data, expected_version: editing.version },
        });
      else await mutations.create.mutateAsync(parsed.data);
      reset();
    } catch (e) {
      setError(e instanceof ApiError ? e.body.message : "Save failed");
    }
  };
  return (
    <Screen title="Tags" description="Create, rename, color, and delete tags.">
      <Card className="max-w-2xl shadow-sm">
        <form onSubmit={submit} className="flex flex-wrap items-end gap-4 p-5">
          <Field label="Name" error={error || undefined}>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Color">
            <span className="relative block size-10 shrink-0 cursor-pointer rounded-full border border-input bg-background p-1 shadow-sm focus-within:ring-2 focus-within:ring-ring">
              <span
                aria-hidden
                className="block size-full rounded-full"
                style={{ backgroundColor: color }}
              />
              <Input
                aria-label="Color"
                type="color"
                className="absolute inset-0 size-full cursor-pointer opacity-0"
                value={color}
                onChange={(e) => setColor(e.target.value)}
              />
            </span>
          </Field>
          <Button>
            {editing ? (
              <>
                <Pencil data-icon="inline-start" />
                Save tag
              </>
            ) : (
              <>
                <Plus data-icon="inline-start" />
                Create tag
              </>
            )}
          </Button>
          {editing && (
            <Button type="button" variant="outline" onClick={reset}>
              Cancel
            </Button>
          )}
        </form>
      </Card>
      {query.isPending ? (
        <Loading label="Loading tags…" />
      ) : query.isError ? (
        <ErrorMessage error={query.error} />
      ) : query.data.length === 0 ? (
        <Empty label="No tags yet." />
      ) : (
        <ul className="grid max-w-2xl gap-2">
          {query.data.map((t) => (
            <li
              className="flex items-center justify-between rounded-xl border bg-card p-4 shadow-sm"
              key={t.id}
            >
              <span className="flex items-center gap-3 font-medium">
                <span
                  className="inline-block size-3 rounded-full ring-4 ring-muted"
                  style={{ background: t.color }}
                />
                {t.name}
              </span>
              <span className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => edit(t)}>
                  <Pencil data-icon="inline-start" />
                  Edit
                </Button>
                <ConfirmAction
                  destructive
                  label="Delete"
                  title={`Delete tag ${t.name}?`}
                  description="Notes keep their content, but this tag will be removed from them."
                  onConfirm={() => {
                    void mutations.remove
                      .mutateAsync({ id: t.id, version: t.version })
                      .catch((e) =>
                        setError(
                          e instanceof ApiError
                            ? e.body.message
                            : "Delete failed",
                        ),
                      );
                  }}
                />
              </span>
            </li>
          ))}
        </ul>
      )}
    </Screen>
  );
}

export function SettingsScreen() {
  const query = useQuery({
    queryKey: queryKeys.settings.all,
    queryFn: api.settings.get,
  });
  return (
    <Screen title="Settings" description="Email and IANA display timezone.">
      {query.isPending ? (
        <Loading label="Loading settings…" />
      ) : query.isError ? (
        <ErrorMessage error={query.error} />
      ) : (
        <SettingsForm settings={query.data} />
      )}
    </Screen>
  );
}
function SettingsForm({
  settings,
}: {
  settings: { email: string; timezone: string; version: number };
}) {
  const [email, setEmail] = useState(settings.email);
  const [timezone, setTimezone] = useState(settings.timezone);
  const [error, setError] = useState("");
  const mutation = useSettingsMutation();
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const parsed = settingsFormSchema.safeParse({
      email,
      timezone,
      expected_version: settings.version,
    });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Invalid settings");
      return;
    }
    try {
      await mutation.mutateAsync(parsed.data);
      setError("");
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 409
          ? "Settings changed elsewhere. Your values are preserved; reload to compare."
          : e instanceof Error
            ? e.message
            : "Save failed",
      );
    }
  };
  return (
    <Card className="max-w-2xl shadow-sm">
      <CardHeader>
        <CardTitle>Workspace preferences</CardTitle>
        <CardDescription>
          These settings apply to every view and reminder.
        </CardDescription>
      </CardHeader>
      <form onSubmit={submit}>
        <CardContent className="flex flex-col gap-5">
          {error && (
            <p
              role="alert"
              className="rounded-lg bg-destructive/5 p-3 text-sm text-destructive"
            >
              {error}
            </p>
          )}
          <Field label="Email">
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </Field>
          <Field label="IANA timezone">
            <Input
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              placeholder="Europe/Budapest"
            />
          </Field>
          <p className="rounded-lg bg-muted p-3 text-sm leading-relaxed text-muted-foreground">
            Timezone changes affect display only. Scheduled instants stay
            unchanged.
          </p>
        </CardContent>
        <CardFooter>
          <Button disabled={mutation.isPending}>
            {mutation.isPending ? "Saving…" : "Save settings"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}

export function NotificationsScreen() {
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: [...queryKeys.notifications.all, page],
    queryFn: () => api.notifications(page, 20),
  });
  return (
    <Screen
      title="Notifications"
      description="Persistent reminder history. History never creates live toasts."
    >
      {query.isPending ? (
        <Loading label="Loading notifications…" />
      ) : query.isError ? (
        <ErrorMessage error={query.error} />
      ) : query.data.items.length === 0 ? (
        <Empty label="No notifications yet." />
      ) : (
        <>
          <ul className="grid gap-3 lg:grid-cols-2">
            {query.data.items.map((n) => (
              <li
                key={n.id}
                className="flex gap-4 rounded-xl border bg-card p-5 shadow-sm"
              >
                <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                  <Bell />
                </span>
                <div>
                  <strong>{n.title}</strong>
                  <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                    Scheduled {new Date(n.scheduled_at).toLocaleString()} ·
                    recorded {new Date(n.created_at).toLocaleString()}
                  </p>
                </div>
              </li>
            ))}
          </ul>
          <Pagination
            page={query.data.page}
            pageSize={query.data.page_size}
            total={query.data.total}
            onPage={setPage}
          />
        </>
      )}
    </Screen>
  );
}
export function NotFoundScreen() {
  return (
    <Screen
      title="Page not found"
      description="The requested page does not exist."
    />
  );
}
function Empty({ label }: { label: string }) {
  return (
    <EmptyPrimitive className="rounded-2xl border bg-card py-14 shadow-sm">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <FilePlus2 />
        </EmptyMedia>
        <EmptyTitle>Nothing here yet</EmptyTitle>
        <EmptyDescription>{label}</EmptyDescription>
      </EmptyHeader>
    </EmptyPrimitive>
  );
}

function Loading({ label }: { label: string }) {
  return (
    <div
      role="status"
      aria-label={label}
      className="grid gap-3 rounded-2xl border bg-card p-6"
    >
      <Skeleton className="h-5 w-40" />
      <Skeleton className="h-20 w-full" />
      <span className="sr-only">{label}</span>
    </div>
  );
}
