import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

export const project = process.env.E2E_COMPOSE_PROJECT ?? "notetaker-e2e";
const repo = fileURLToPath(new URL("../../../", import.meta.url));
export type Note = { id:string; title:string; body:string; starts_at:string; active:boolean; version:number; series_id:string|null; recurrence_key:string|null; reminder_offsets_minutes:number[]; tags:{id:string}[] };
export type Series = { id:string; version:number; end_date:string; timezone:string };

export function compose(...args:string[]):string {
  return execFileSync("docker", ["compose", "-p", project, ...args], { cwd:repo, encoding:"utf8" });
}
export function sql(statement:string):string {
  return compose("exec", "-T", "postgres", "psql", "-v", "ON_ERROR_STOP=1", "-U", "notetaker", "-d", "notetaker", "-Atc", statement).trim();
}
export async function resetData(request:APIRequestContext):Promise<void> {
  sql(`TRUNCATE notifications, reminder_deliveries, reminder_rules, occurrence_exceptions, note_tags, series_tags, series_reminder_templates, outbox_events, notes, recurrence_series, tags, user_settings RESTART IDENTITY CASCADE; INSERT INTO user_settings (id,email,timezone,version) VALUES ('00000000-0000-0000-0000-000000000001','demo@example.test','Europe/Budapest',1);`);
  await request.delete("http://127.0.0.1:"+(process.env.E2E_MAILPIT_PORT??"18025")+"/api/v1/messages").catch(()=>undefined);
}
async function json<T>(response:Awaited<ReturnType<APIRequestContext["get"]>>):Promise<T>{
  expect(response.ok(), `${response.url()}: ${await response.text()}`).toBeTruthy();
  return response.json() as Promise<T>;
}
export async function createNote(request:APIRequestContext, title:string, startsAt:Date, reminders:number[]=[]):Promise<Note>{
  return json(await request.post("/api/v1/notes",{data:{title,body:`Body for ${title}`,starts_at:startsAt.toISOString(),active:true,tag_ids:[],reminder_offsets_minutes:reminders}}));
}
export async function createSeries(request:APIRequestContext,title:string,start:Date,countDays=5):Promise<Series>{
  const local=start.toISOString().slice(0,19); const end=new Date(start.getTime()+countDays*86400000).toISOString().slice(0,10);
  return json(await request.post("/api/v1/series",{data:{title,body:`Body for ${title}`,starts_at:start.toISOString(),active:true,tag_ids:[],reminder_offsets_minutes:[],local_start:local,timezone:"UTC",frequency:"daily",end_date:end}}));
}
export async function notes(request:APIRequestContext,trash=false):Promise<Note[]>{return (await json<{items:Note[]}>(await request.get(`/api/v1/notes?trash=${trash}&page_size=100`))).items;}
export async function note(request:APIRequestContext,id:string):Promise<Note>{return json(await request.get(`/api/v1/notes/${id}`));}
export async function poll<T>(fn:()=>Promise<T>, accept:(value:T)=>boolean, timeout=12_000):Promise<T>{
  const end=Date.now()+timeout; let last:T; do { last=await fn(); if(accept(last))return last; await new Promise(r=>setTimeout(r,250)); }while(Date.now()<end); throw new Error(`Polling timed out; last value: ${JSON.stringify(last!)}`);
}
export async function openApp(page:Page,path:string):Promise<void>{await page.goto(path); await expect(page.getByRole("heading",{level:1})).toBeVisible();}
export function card(page:Page,title:string){return page.locator("li").filter({has:page.getByRole("heading",{name:title,exact:true})});}
export async function editCard(page:Page,title:string,nextTitle:string,body?:string):Promise<void>{
  const row=card(page,title); await row.getByRole("button",{name:"Edit"}).click(); const form=page.getByRole("form",{name:"Edit note"}); await form.getByLabel("Title").fill(nextTitle); if(body!==undefined)await form.getByLabel("Body").fill(body); await form.getByRole("button",{name:"Save note",exact:true}).click();
}
export function redisPublish(payload:object):void {compose("exec","-T","redis","redis-cli","PUBLISH","notetaker.events",JSON.stringify(payload));}
export async function mailpitMessages(request:APIRequestContext):Promise<any[]>{const r=await request.get("http://127.0.0.1:"+(process.env.E2E_MAILPIT_PORT??"18025")+"/api/v1/messages"); if(!r.ok())throw new Error(`Mailpit ${r.status()}`); const data=await r.json(); return data.messages??data.items??[];}
