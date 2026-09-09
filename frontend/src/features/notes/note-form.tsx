import { useState, type FormEvent } from "react";
import { DateTime } from "luxon";
import type { Note, NoteWrite, ReminderOffset, Tag } from "../../api/contracts";
import { api, ApiError } from "../../api/client";
import { useNoteMutations } from "../../api/mutations";
import { noteFormSchema } from "../../forms/schemas";
import { Button } from "../../components/ui/button";
import { Field, Input } from "../../components/ui/input";

type Draft = { title: string; body: string; starts_at: string; active: boolean; tag_ids: string[]; reminder_offsets_minutes: ReminderOffset[] };
const localDate = (iso: string, timezone: string) => DateTime.fromISO(iso,{setZone:true}).setZone(timezone).toFormat("yyyy-LL-dd\'T\'HH:mm");
const initial = (timezone:string,note?: Note): Draft => note ? { title:note.title, body:note.body, starts_at:localDate(note.starts_at,timezone), active:note.active, tag_ids:note.tags.map(t=>t.id), reminder_offsets_minutes:note.reminder_offsets_minutes } : { title:"", body:"", starts_at:localDate(new Date(Date.now()+3600000).toISOString(),timezone), active:true, tag_ids:[], reminder_offsets_minutes:[] };
function payload(draft: Draft, timezone: string): NoteWrite { const instant=DateTime.fromISO(draft.starts_at,{zone:timezone}); return {...draft, starts_at:instant.isValid?(instant.toISO()??draft.starts_at):draft.starts_at}; }
export function NoteForm({ note, tags, timezone, onSaved, onCancel }: { note?: Note; tags: Tag[]; timezone: string; onSaved: () => void; onCancel: () => void }) {
  // Deliberately initialize once. Query invalidation/realtime rerenders must not overwrite a dirty draft.
  const [draft,setDraft]=useState<Draft>(()=>initial(timezone,note));
  const [errors,setErrors]=useState<Record<string,string>>({});
  const mutations=useNoteMutations(); const mutation=note?mutations.update:mutations.create;
  const [conflict,setConflict]=useState<unknown>(null);
  const submit=async(e:FormEvent)=>{e.preventDefault();setErrors({});setConflict(null);const parsed=noteFormSchema.safeParse(payload(draft,timezone));if(!parsed.success){setErrors(Object.fromEntries(parsed.error.issues.map(i=>[String(i.path[0]),i.message])));return;}try{if(note){const expected_series_version=note.series_id?(await api.series.get(note.series_id)).version:undefined;await mutations.update.mutateAsync({id:note.id,value:{...parsed.data,expected_version:note.version,...(expected_series_version===undefined?{}:{expected_series_version})}});}else await mutations.create.mutateAsync(parsed.data);onSaved();}catch(error){if(error instanceof ApiError&&error.status===409)setConflict(error.body.current);else setErrors({form:error instanceof Error?error.message:"Save failed"});}};
  const toggleTag=(id:string)=>setDraft(d=>({...d,tag_ids:d.tag_ids.includes(id)?d.tag_ids.filter(x=>x!==id):[...d.tag_ids,id]}));
  const toggleReminder=(value:ReminderOffset)=>setDraft(d=>({...d,reminder_offsets_minutes:d.reminder_offsets_minutes.includes(value)?d.reminder_offsets_minutes.filter(x=>x!==value):[...d.reminder_offsets_minutes,value]}));
  return <form className="grid gap-4 rounded-lg border bg-white p-5 shadow-sm" onSubmit={submit} aria-label={note?"Edit note":"Create note"}>
    <h2 className="text-lg font-bold">{note?"Edit note":"New note"}</h2>
    {conflict!==null&&<div role="alert" className="rounded border border-amber-400 bg-amber-50 p-3"><strong>This note changed elsewhere.</strong><p className="text-sm">Your draft is still here. Cancel and reopen to load the latest version, or copy your changes first.</p><details><summary>Latest server value</summary><pre className="overflow-auto text-xs">{JSON.stringify(conflict,null,2)}</pre></details></div>}
    {errors.form&&<p role="alert" className="text-red-700">{errors.form}</p>}
    <Field label="Title" error={errors.title}><Input value={draft.title} onChange={e=>setDraft({...draft,title:e.target.value})}/></Field>
    <Field label="Body" error={errors.body}><textarea className="min-h-28 rounded-md border border-slate-300 p-3" value={draft.body} onChange={e=>setDraft({...draft,body:e.target.value})}/></Field>
    <Field label="Date and time" error={errors.starts_at}><Input type="datetime-local" value={draft.starts_at} onChange={e=>setDraft({...draft,starts_at:e.target.value})}/></Field>
    <label className="flex gap-2"><input type="checkbox" checked={draft.active} onChange={e=>setDraft({...draft,active:e.target.checked})}/> Active</label>
    <fieldset><legend className="mb-1 text-sm font-medium">Tags</legend><div className="flex flex-wrap gap-3">{tags.map(tag=><label key={tag.id} className="flex items-center gap-1 text-sm"><input type="checkbox" checked={draft.tag_ids.includes(tag.id)} onChange={()=>toggleTag(tag.id)}/><span className="size-3 rounded-full" style={{backgroundColor:tag.color}}/>{tag.name}</label>)}</div></fieldset>
    <fieldset><legend className="mb-1 text-sm font-medium">Reminders</legend><div className="flex flex-wrap gap-3">{([[10,"10 minutes"],[60,"1 hour"],[1440,"1 day"]] as const).map(([value,label])=><label key={value} className="text-sm"><input type="checkbox" checked={draft.reminder_offsets_minutes.includes(value)} onChange={()=>toggleReminder(value)}/> {label}</label>)}</div></fieldset>
    <div className="flex gap-2"><Button disabled={mutation.isPending}>{mutation.isPending?"Saving…":"Save"}</Button><Button type="button" variant="outline" onClick={onCancel}>Cancel</Button></div>
  </form>;
}
