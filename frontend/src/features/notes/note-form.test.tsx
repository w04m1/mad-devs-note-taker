import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Note } from "../../api/contracts";
import { manualNoteInstant, NoteForm } from "./note-form";

const note: Note={id:"10000000-0000-4000-8000-000000000001",title:"Original",body:"Body",starts_at:"2026-04-01T10:00:00Z",active:true,tags:[],reminder_offsets_minutes:[10],version:1,created_at:"2026-01-01T00:00:00Z",updated_at:"2026-01-01T00:00:00Z",deleted_at:null,series_id:null,recurrence_key:null};
const wrapper=(client:QueryClient)=>(<QueryClientProvider client={client}><NoteForm note={note} tags={[]} timezone="UTC" onSaved={vi.fn()} onCancel={vi.fn()}/></QueryClientProvider>);
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
describe("note form",()=>{
 it("rejects a DST gap and uses the earlier instant in an overlap",()=>{expect(manualNoteInstant("2026-03-29T02:30","Europe/Budapest")).toBeNull();expect(manualNoteInstant("2026-10-25T02:30","Europe/Budapest")).toBe("2026-10-25T02:30:00.000+02:00")});
 it("keeps a dirty draft when its parent rerenders with refreshed data",async()=>{const client=new QueryClient({defaultOptions:{mutations:{retry:false}}});const view=render(wrapper(client));const title=screen.getByLabelText("Title");await userEvent.clear(title);await userEvent.type(title,"My local draft");view.rerender(<QueryClientProvider client={client}><NoteForm note={{...note,title:"Remote title",version:2}} tags={[]} timezone="UTC" onSaved={vi.fn()} onCancel={vi.fn()}/></QueryClientProvider>);expect(screen.getByLabelText("Title")).toHaveValue("My local draft")});
 it("shows a 409 conflict and preserves the submitted draft",async()=>{const client=new QueryClient({defaultOptions:{mutations:{retry:false}}});vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response(JSON.stringify({code:"version_conflict",message:"Changed",field_errors:null,current:{...note,title:"Remote title",version:2}}),{status:409,headers:{"content-type":"application/json"}})));render(wrapper(client));const title=screen.getByLabelText("Title");await userEvent.clear(title);await userEvent.type(title,"My local draft");fireEvent.submit(screen.getByRole("form",{name:"Edit note"}));await waitFor(()=>expect(screen.getByText("This note changed elsewhere.")).toBeInTheDocument());expect(title).toHaveValue("My local draft");expect(screen.getByText("Latest server value")).toBeInTheDocument()});
});
