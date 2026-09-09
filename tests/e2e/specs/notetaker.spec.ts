import { test, expect, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { card, compose, createNote, createSeries, editCard, mailpitMessages, note, notes, openApp, poll, redisPublish, resetData, sql } from "../helpers/harness";

let contexts:BrowserContext[]=[];
async function client(browser:Browser, timezoneId="UTC"):Promise<Page>{const context=await browser.newContext({timezoneId}); contexts.push(context); return context.newPage();}
test.describe.configure({mode:"serial"});
test.afterEach(async()=>{await Promise.all(contexts.splice(0).map(c=>c.close()));});
test.beforeEach(async({request})=>resetData(request));

async function setTimezone(request:any,timezone:string){const current=await (await request.get("/api/v1/settings")).json(); const response=await request.patch("/api/v1/settings",{data:{email:current.email,timezone,expected_version:current.version}}); expect(response.ok(),await response.text()).toBeTruthy();}
function localParts(iso:string,zone:string){const parts=new Intl.DateTimeFormat("en-CA",{timeZone:zone,year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).formatToParts(new Date(iso)); return Object.fromEntries(parts.map(p=>[p.type,p.value]));}

test("realtime edits reach a second client and Upcoming moves a note to past",async({browser,request})=>{
  const crossing=await createNote(request,"Crossing soon",new Date(Date.now()+10_000));
  await createNote(request,"Realtime original",new Date(Date.now()+3_600_000));
  const a=await client(browser), b=await client(browser);
  await openApp(b,"/upcoming"); await expect(b.getByText("Realtime original",{exact:true})).toBeVisible();
  const past=b.getByRole("region",{name:/Past active/}); await expect(b.getByText(crossing.title,{exact:true})).toBeVisible(); await expect(past.getByText(crossing.title,{exact:true})).toHaveCount(0);
  await openApp(a,"/notes"); await editCard(a,"Realtime original","Realtime changed");
  await expect(b.getByText("Realtime changed",{exact:true})).toBeVisible({timeout:8_000});
  await expect(past.getByText(crossing.title,{exact:true})).toBeVisible({timeout:15_000});
});

test("a due reminder toasts once per tab, emails once, and persists without replay",async({browser,request})=>{
  const a=await client(browser), b=await client(browser); await openApp(a,"/notifications"); await openApp(b,"/notifications");
  await createNote(request,"One delivery",new Date(Date.now()+607_000),[10]);
  await expect(a.getByRole("status").filter({hasText:"A reminder is due"})).toHaveCount(1,{timeout:15_000});
  await expect(b.getByRole("status").filter({hasText:"A reminder is due"})).toHaveCount(1,{timeout:15_000});
  const history=await poll(async()=>{const r=await request.get("/api/v1/notifications?page_size=20"); return r.json();},v=>v.total===1,12_000);
  const notification=history.items[0];
  await poll(()=>mailpitMessages(request),m=>m.length===1,12_000);
  redisPublish({event_id:"11111111-1111-4111-8111-111111111111",type:"notification.created",occurred_at:new Date().toISOString(),entity_id:notification.id,version:1,series_id:null});
  await a.waitForTimeout(600); await expect(a.getByRole("status").filter({hasText:"A reminder is due"})).toHaveCount(1);
  await a.reload(); await expect(a.getByText("One delivery",{exact:true})).toBeVisible();
  await expect(a.getByRole("status").filter({hasText:"A reminder is due"})).toHaveCount(0);
  expect((await mailpitMessages(request)).length).toBe(1);
});

test("calendar drag uses the profile timezone and persists the moved instant",async({browser,request})=>{
  const zone="America/Los_Angeles"; await setTimezone(request,zone);
  const start=new Date(Date.now()+7*86400000); start.setUTCHours(18,30,0,0); const created=await createNote(request,"Timezone drag",start);
  const before=localParts(created.starts_at,zone); const sourceDate=`${before.year}-${before.month}-${before.day}`;
  const targetDate=new Date(start.getTime()+86400000); const tp=localParts(targetDate.toISOString(),zone); const target=`${tp.year}-${tp.month}-${tp.day}`;
  const page=await client(browser,"Asia/Tokyo"); await openApp(page,`/calendar?view=dayGridMonth&date=${sourceDate}`);
  const event=page.locator(".fc-event").filter({hasText:"Timezone drag"}); await expect(event).toBeVisible();
  await event.dragTo(page.locator(`.fc-daygrid-day[data-date="${target}"]`));
  const moved=await poll(()=>note(request,created.id),n=>n.starts_at!==created.starts_at);
  const after=localParts(moved.starts_at,zone); expect(`${after.hour}:${after.minute}`).toBe(`${before.hour}:${before.minute}`); expect(`${after.year}-${after.month}-${after.day}`).toBe(target);
  await page.reload(); await expect(page.locator(`.fc-daygrid-day[data-date="${target}"]`).getByText("Timezone drag",{exact:true})).toBeVisible();
});

test("concurrent editors preserve a stale draft and show an explicit conflict",async({browser,request})=>{
  await createNote(request,"Concurrent base",new Date(Date.now()+3_600_000));
  const a=await client(browser),b=await client(browser); await openApp(a,"/notes"); await openApp(b,"/notes");
  await card(a,"Concurrent base").getByRole("button",{name:"Edit"}).click(); await card(b,"Concurrent base").getByRole("button",{name:"Edit"}).click();
  const af=a.getByRole("form",{name:"Edit note"}), bf=b.getByRole("form",{name:"Edit note"});
  await af.getByLabel("Title").fill("Winner title"); await bf.getByLabel("Body").fill("losing draft must remain");
  await af.getByRole("button",{name:"Save",exact:true}).click(); await expect(a.getByText("Winner title",{exact:true})).toBeVisible();
  await expect(bf.getByLabel("Body")).toHaveValue("losing draft must remain"); await bf.getByRole("button",{name:"Save",exact:true}).click();
  await expect(b.getByRole("alert").filter({hasText:"This note changed elsewhere."})).toBeVisible(); await expect(bf.getByLabel("Body")).toHaveValue("losing draft must remain");
});

test("recurrence keeps earlier edits and cancellation when the future is split",async({browser,request})=>{
  const start=new Date(Date.now()+2*86400000); start.setUTCHours(12,0,0,0); await createSeries(request,"Series base",start,5);
  const page=await client(browser); await openApp(page,"/notes"); let rows=await notes(request); expect(rows.length).toBe(6);
  const first=rows[0],second=rows[1],third=rows[2];
  await card(page,"Series base").first().getByRole("button",{name:"Edit"}).click(); await page.getByRole("button",{name:"Only this occurrence"}).click(); const one=page.getByRole("form",{name:"Edit note"}); await one.getByLabel("Title").fill("Earlier exception"); await one.getByRole("button",{name:"Save",exact:true}).click();
  await expect(page.getByText("Earlier exception",{exact:true})).toBeVisible();
  rows=await notes(request); const secondNow=rows.find(n=>n.id===second.id)!; const secondCard=card(page,"Series base").filter({has:page.locator(`time`)}).nth(0); // first remaining base is the second slot
  page.once("dialog",d=>d.accept()); await secondCard.getByRole("button",{name:"Trash"}).click(); await poll(()=>notes(request,true),v=>v.some(n=>n.id===secondNow.id));
  await page.reload(); const baseCards=card(page,"Series base"); await expect(baseCards).toHaveCount(4);
  await baseCards.first().getByRole("button",{name:"Edit"}).click(); await page.getByRole("button",{name:"This and future occurrences"}).click(); const future=page.getByRole("form",{name:"Edit this and future occurrences"}); await future.getByLabel("Title").fill("Replacement future"); await future.getByRole("button",{name:"Save series"}).click();
  const visible=await notes(request); expect(visible.find(n=>n.id===first.id)?.title).toBe("Earlier exception"); expect((await notes(request,true)).some(n=>n.id===second.id)).toBeTruthy(); expect(visible.filter(n=>n.title==="Replacement future").length).toBeGreaterThanOrEqual(1); expect(visible.filter(n=>n.title==="Series base").length).toBe(0);
});

test("trash and restore update both clients and reinstate only future reminder work",async({browser,request})=>{
  const created=await createNote(request,"Restore across clients",new Date(Date.now()+3_600_000),[10]); const a=await client(browser),b=await client(browser); await openApp(a,"/notes"); await openApp(b,"/notes");
  pageAccept(a); await card(a,created.title).getByRole("button",{name:"Trash"}).click(); await expect(card(b,created.title)).toHaveCount(0,{timeout:8_000});
  await openApp(b,"/trash"); await expect(b.getByText(created.title,{exact:true})).toBeVisible();
  expect(sql(`SELECT state::text FROM reminder_deliveries d JOIN reminder_rules r ON r.id=d.reminder_rule_id WHERE r.note_id='${created.id}' ORDER BY d.cycle_number DESC LIMIT 1`)).toBe("cancelled");
  await b.getByRole("button",{name:"Restore"}).click(); await expect(b.getByText("Trash is empty.")).toBeVisible(); await expect(card(a,created.title)).toBeVisible({timeout:8_000});
  expect(sql(`SELECT state::text FROM reminder_deliveries d JOIN reminder_rules r ON r.id=d.reminder_rule_id WHERE r.note_id='${created.id}' ORDER BY d.cycle_number DESC LIMIT 1`)).toBe("pending");
  expect(Number(sql(`SELECT count(*) FROM reminder_deliveries d JOIN reminder_rules r ON r.id=d.reminder_rule_id WHERE r.note_id='${created.id}' AND d.due_at <= now()`))).toBe(0);
});
function pageAccept(page:Page){page.once("dialog",d=>d.accept());}
