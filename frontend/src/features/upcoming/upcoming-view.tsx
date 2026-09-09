import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { DateTime } from "luxon";
import { api } from "../../api/client";
import { queryKeys } from "../../api/query-keys";
import type { Note, UpcomingResponse } from "../../api/contracts";

export function nextUpcomingDelay(data: UpcomingResponse | undefined, timezone: string, nowMs=Date.now()): number {
  const serverMs=data?.server_now?DateTime.fromISO(data.server_now,{setZone:true}).toMillis():nowMs;
  const serverNow=DateTime.fromMillis(serverMs,{zone:timezone});
  const midnight=serverNow.plus({days:1}).startOf("day").toMillis();
  const transition=data?.next_transition_at ? DateTime.fromISO(data.next_transition_at,{setZone:true}).toMillis() : Infinity;
  return Math.max(0,Math.min(midnight,transition)-serverMs);
}
export function useUpcomingRefresh(data:UpcomingResponse|undefined,timezone:string){const client=useQueryClient();useEffect(()=>{const refresh=()=>void client.invalidateQueries({queryKey:queryKeys.upcoming.all});const delay=nextUpcomingDelay(data,timezone);const timer=window.setTimeout(refresh,Math.min(delay,2_147_000_000));const fallback=window.setInterval(refresh,60_000);const visible=()=>{if(document.visibilityState==="visible")refresh()};window.addEventListener("focus",refresh);document.addEventListener("visibilitychange",visible);return()=>{clearTimeout(timer);clearInterval(fallback);window.removeEventListener("focus",refresh);document.removeEventListener("visibilitychange",visible)}},[client,data?.next_transition_at,data?.server_now,timezone])}
const format=(iso:string,timezone:string)=>DateTime.fromISO(iso,{setZone:true}).setZone(timezone).toLocaleString(DateTime.DATETIME_MED);
function Group({title,notes,timezone,onOpen}:{title:string;notes:Note[];timezone:string;onOpen:(note:Note)=>void}){return <section aria-labelledby={`upcoming-${title.replaceAll(" ","-")}`}><h2 id={`upcoming-${title.replaceAll(" ","-")}`} className="mb-2 text-lg font-bold">{title} <span className="text-sm font-normal text-slate-500">({notes.length})</span></h2>{notes.length===0?<p className="rounded border border-dashed bg-white p-4 text-slate-500">No notes in this section.</p>:<ul className="grid gap-2">{notes.map(n=><li key={n.id}><button className="w-full rounded border bg-white p-4 text-left hover:border-blue-500" onClick={()=>onOpen(n)}><strong>{n.title}</strong><time dateTime={n.starts_at} className="mt-1 block text-sm text-slate-600">{format(n.starts_at,timezone)}</time></button></li>)}</ul>}</section>}
export function UpcomingView({timezone,onOpen}:{timezone:string;onOpen:(note:Note)=>void}){const query=useQuery({queryKey:queryKeys.upcoming.all,queryFn:api.upcoming});useUpcomingRefresh(query.data,timezone);if(query.isPending)return <p role="status">Loading upcoming notes…</p>;if(query.isError)return <p role="alert">Upcoming notes could not be loaded.</p>;return <div className="grid gap-6 xl:grid-cols-3" aria-live="polite" aria-busy={query.isFetching}><Group title="Today" notes={query.data.today} timezone={timezone} onOpen={onOpen}/><Group title="This week" notes={query.data.this_week} timezone={timezone} onOpen={onOpen}/><Group title="Past active" notes={query.data.past} timezone={timezone} onOpen={onOpen}/></div>}
