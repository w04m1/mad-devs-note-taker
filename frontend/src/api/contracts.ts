export type UUID = string;
export type ISODateTime = string;
export interface Tag { id: UUID; name: string; color: string; version: number }
export interface Note { id: UUID; title: string; body: string; starts_at: ISODateTime; active: boolean; tags: Tag[]; reminder_offsets_minutes: ReminderOffset[]; version: number; created_at: ISODateTime; updated_at: ISODateTime; deleted_at: ISODateTime | null; series_id: UUID | null; recurrence_key: string | null }
export interface Settings { email: string; timezone: string; version: number }
export interface Page<T> { items: T[]; total: number; page: number; page_size: number }
export type ReminderOffset = 10 | 60 | 1440;
export type SortField = "starts_at" | "updated_at";
export type Direction = "asc" | "desc";
export interface NoteListParams { q?: string; tag_id?: UUID[]; active?: boolean; starts_from?: ISODateTime; starts_to?: ISODateTime; trash?: boolean; sort?: SortField; direction?: Direction; page?: number; page_size?: number }
export interface NoteWrite { title: string; body: string; starts_at: ISODateTime; active: boolean; tag_ids: UUID[]; reminder_offsets_minutes: ReminderOffset[] }
export interface NoteUpdate extends NoteWrite { expected_version: number; expected_series_version?: number }
export interface TagWrite { name: string; color: string }
export interface SettingsUpdate { email: string; timezone: string; expected_version: number }
export type Frequency = "daily" | "weekly" | "monthly";
export interface SeriesCreate extends NoteWrite { local_start: string; timezone: string; frequency: Frequency; end_date: string }
export interface ApiErrorBody { code: string; message: string; field_errors: Record<string,string | string[]> | null; current: unknown | null }
export type EventType = "note.created"|"note.updated"|"note.deleted"|"note.restored"|"series.updated"|"tag.created"|"tag.updated"|"tag.deleted"|"settings.updated"|"notification.created"|"resync_required";
export interface RealtimeEvent { event_id: UUID; type: EventType; occurred_at: ISODateTime; entity_id: UUID | null; version: number | null; series_id: UUID | null }
export interface Notification { id: UUID; reminder_delivery_id: UUID; title: string; body: string; scheduled_at: ISODateTime; created_at: ISODateTime }

export interface RecurrenceSeries { id: UUID; lineage_id: UUID; predecessor_id: UUID | null; local_start: string; timezone: string; frequency: Frequency; end_date: string; version: number }
export interface SeriesMutationVersion { expected_version: number }
export interface SeriesSplit extends SeriesCreate { recurrence_key: string; expected_version: number; expected_occurrence_version: number }
export interface CalendarParams { starts_from: ISODateTime; starts_to: ISODateTime }
export interface UpcomingResponse { today: Note[]; this_week: Note[]; past: Note[]; server_now: ISODateTime; next_transition_at: ISODateTime | null }
