import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Note } from "../../api/contracts";
import { manualNoteChoices, manualNoteInstant, NoteForm } from "./note-form";

vi.mock("../../components/date-time-picker", () => ({
  DateTimePicker: ({
    label,
    value,
    onChange,
  }: {
    label: string;
    value: string;
    onChange: (value: string) => void;
  }) => (
    <input
      aria-label={label}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}));

const note: Note={id:"10000000-0000-4000-8000-000000000001",title:"Original",body:"Body",starts_at:"2026-04-01T10:00:00Z",active:true,tags:[],reminder_offsets_minutes:[10],version:1,created_at:"2026-01-01T00:00:00Z",updated_at:"2026-01-01T00:00:00Z",deleted_at:null,series_id:null,recurrence_key:null};
const wrapper=(client:QueryClient)=>(<QueryClientProvider client={client}><NoteForm note={note} tags={[]} timezone="UTC" onSaved={vi.fn()} onCancel={vi.fn()}/></QueryClientProvider>);
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
describe("note form",()=>{
 it("rejects a DST gap and requires one of both overlap instants",()=>{
  expect(manualNoteChoices("2026-03-29T02:30","Europe/Budapest")).toEqual([]);
  const choices=manualNoteChoices("2026-10-25T02:30","Europe/Budapest");
  expect(choices).toEqual(["2026-10-25T02:30:00.000+02:00","2026-10-25T02:30:00.000+01:00"]);
  expect(manualNoteInstant("2026-10-25T02:30","Europe/Budapest")).toBeNull();
  expect(manualNoteInstant("2026-10-25T02:30","Europe/Budapest",choices[1])).toBe(choices[1]);
 });
 it("reports a nonexistent local time without submitting",async()=>{
  const client=new QueryClient({defaultOptions:{mutations:{retry:false}}});
  const fetchMock=vi.fn(); vi.stubGlobal("fetch",fetchMock);
  render(<QueryClientProvider client={client}><NoteForm note={note} tags={[]} timezone="Europe/Budapest" onSaved={vi.fn()} onCancel={vi.fn()}/></QueryClientProvider>);
  fireEvent.change(screen.getByLabelText("Date and time"),{target:{value:"2026-03-29T02:30"}});
  fireEvent.submit(screen.getByRole("form",{name:"Edit note"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("does not exist in the selected timezone");
  expect(fetchMock).not.toHaveBeenCalled();
 });
 it("presents both overlap offsets as an accessible required choice",async()=>{
  const client=new QueryClient({defaultOptions:{mutations:{retry:false}}});
  render(<QueryClientProvider client={client}><NoteForm note={note} tags={[]} timezone="Europe/Budapest" onSaved={vi.fn()} onCancel={vi.fn()}/></QueryClientProvider>);
  fireEvent.change(screen.getByLabelText("Date and time"),{target:{value:"2026-10-25T02:30"}});
  const group=screen.getByRole("group",{name:"This time occurs twice. Choose one."});
  const first=screen.getByRole("radio",{name:/First occurrence — UTC\+02:00/});
  const second=screen.getByRole("radio",{name:/Second occurrence — UTC\+01:00/});
  expect(group).toContainElement(first); expect(group).toContainElement(second);
  expect(first).not.toBeChecked(); expect(second).not.toBeChecked();
  fireEvent.submit(screen.getByRole("form",{name:"Edit note"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("Choose which occurrence");
  await userEvent.click(second);
  expect(second).toBeChecked(); expect(first).not.toBeChecked();
  const fetchMock=vi.fn().mockResolvedValue(new Response(JSON.stringify(note),{status:200,headers:{"content-type":"application/json"}}));
  vi.stubGlobal("fetch",fetchMock);
  fireEvent.submit(screen.getByRole("form",{name:"Edit note"}));
  await waitFor(()=>expect(fetchMock).toHaveBeenCalledOnce());
  const request=fetchMock.mock.calls[0]![1] as RequestInit;
  expect(JSON.parse(String(request.body)).starts_at).toBe("2026-10-25T02:30:00.000+01:00");
 });
 it("keeps a dirty draft when its parent rerenders with refreshed data",async()=>{const client=new QueryClient({defaultOptions:{mutations:{retry:false}}});const view=render(wrapper(client));const title=screen.getByLabelText("Title");await userEvent.clear(title);await userEvent.type(title,"My local draft");view.rerender(<QueryClientProvider client={client}><NoteForm note={{...note,title:"Remote title",version:2}} tags={[]} timezone="UTC" onSaved={vi.fn()} onCancel={vi.fn()}/></QueryClientProvider>);expect(screen.getByLabelText("Title")).toHaveValue("My local draft")});
 it("preserves the exact original instant when the minute field is unchanged",async()=>{
  const precise={...note,starts_at:"2026-10-25T01:30:45.123456Z"};
  const client=new QueryClient({defaultOptions:{mutations:{retry:false}}});
  const fetchMock=vi.fn().mockResolvedValue(new Response(JSON.stringify(precise),{status:200,headers:{"content-type":"application/json"}}));vi.stubGlobal("fetch",fetchMock);
  render(<QueryClientProvider client={client}><NoteForm note={precise} tags={[]} timezone="Europe/Budapest" onSaved={vi.fn()} onCancel={vi.fn()}/></QueryClientProvider>);
  fireEvent.submit(screen.getByRole("form",{name:"Edit note"}));
  await waitFor(()=>expect(fetchMock).toHaveBeenCalledOnce());
  expect(JSON.parse(String((fetchMock.mock.calls[0]![1] as RequestInit).body)).starts_at).toBe(precise.starts_at);
 });
 it("pins the authoring timezone across a parent settings change",async()=>{
  const client=new QueryClient({defaultOptions:{mutations:{retry:false}}});
  const fetchMock=vi.fn().mockResolvedValue(new Response(JSON.stringify(note),{status:200,headers:{"content-type":"application/json"}}));vi.stubGlobal("fetch",fetchMock);
  const view=render(<QueryClientProvider client={client}><NoteForm note={note} tags={[]} timezone="UTC" onSaved={vi.fn()} onCancel={vi.fn()}/></QueryClientProvider>);
  view.rerender(<QueryClientProvider client={client}><NoteForm note={note} tags={[]} timezone="America/New_York" onSaved={vi.fn()} onCancel={vi.fn()}/></QueryClientProvider>);
  fireEvent.change(screen.getByLabelText("Date and time"),{target:{value:"2026-04-02T10:00"}});
  fireEvent.submit(screen.getByRole("form",{name:"Edit note"}));
  await waitFor(()=>expect(fetchMock).toHaveBeenCalledOnce());
  expect(JSON.parse(String((fetchMock.mock.calls[0]![1] as RequestInit).body)).starts_at).toBe("2026-04-02T10:00:00.000Z");
 });
 it("shows a 409 conflict and preserves the submitted draft",async()=>{const client=new QueryClient({defaultOptions:{mutations:{retry:false}}});vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response(JSON.stringify({code:"version_conflict",message:"Changed",field_errors:null,current:{...note,title:"Remote title",version:2}}),{status:409,headers:{"content-type":"application/json"}})));render(wrapper(client));const title=screen.getByLabelText("Title");await userEvent.clear(title);await userEvent.type(title,"My local draft");fireEvent.submit(screen.getByRole("form",{name:"Edit note"}));await waitFor(()=>expect(screen.getByText("This note changed elsewhere.")).toBeInTheDocument());expect(title).toHaveValue("My local draft");expect(screen.getByText("Latest server value")).toBeInTheDocument()});
});
