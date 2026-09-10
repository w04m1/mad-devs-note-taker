import {afterEach,beforeEach,describe,expect,it,vi} from "vitest";
vi.mock("../../api/client",async original=>{const actual=await original<typeof import("../../api/client")>();return {...actual,api:{...actual.api,series:{...actual.api.series,get:vi.fn().mockResolvedValue({id:"s",lineage_id:"s",predecessor_id:null,local_start:"2026-01-01T10:00:00",timezone:"UTC",frequency:"weekly",end_date:"2026-02-01",version:2})}}}});import {cleanup,render,screen,waitFor} from "@testing-library/react";import userEvent from "@testing-library/user-event";import {QueryClient,QueryClientProvider} from "@tanstack/react-query";import {api,ApiError} from "../../api/client";import {RecurringEditChoice,recurrenceStartInstant} from "./series-form";import type {Note} from "../../api/contracts";
const note:Note={id:"n",title:"Series",body:"",starts_at:"2026-01-01T10:00:00Z",active:true,tags:[],reminder_offsets_minutes:[],version:1,created_at:"",updated_at:"",deleted_at:null,series_id:"s",recurrence_key:"2026-01-01T10:00:00Z"};
beforeEach(()=>vi.clearAllMocks());
afterEach(()=>{cleanup();vi.restoreAllMocks()});
it("requires scope choice and explicitly warns before future replacement",async()=>{render(<QueryClientProvider client={new QueryClient()}><RecurringEditChoice note={note} timezone="UTC" tags={[]} onClose={vi.fn()}/></QueryClientProvider>);expect(screen.getByRole("button",{name:"Only this occurrence"})).toBeInTheDocument();await userEvent.click(screen.getByRole("button",{name:"This and future occurrences"}));expect(await screen.findByRole("alert")).toHaveTextContent("Future exceptions will be replaced");expect(screen.getByRole("form",{name:"Edit this and future occurrences"})).toBeInTheDocument()});
it("submits the intent-time series token and preserves the draft on a stale conflict",async()=>{
 const preview=vi.spyOn(api.series,"preview").mockResolvedValue({starts_at:"2026-01-01T10:00:00Z",occurrence_count:5});
 const split=vi.spyOn(api.series,"split").mockRejectedValue(new ApiError(409,{code:"version_conflict",message:"Changed",field_errors:null,current:{id:"s",version:3}}));
 render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><RecurringEditChoice note={note} timezone="UTC" tags={[]} onClose={vi.fn()}/></QueryClientProvider>);
 await userEvent.click(screen.getByRole("button",{name:"This and future occurrences"}));
 const form=await screen.findByRole("form",{name:"Edit this and future occurrences"});
 await userEvent.click(screen.getByRole("button",{name:"Save series"}));
 await waitFor(()=>expect(split).toHaveBeenCalledOnce());
 expect(split).toHaveBeenCalledWith("s",expect.objectContaining({expected_series_version:2}));
 expect(api.series.get).toHaveBeenCalledTimes(1);
 expect(preview).toHaveBeenCalledOnce();
 expect(await screen.findByText(/draft is preserved/)).toBeInTheDocument();
 expect(form).toBeInTheDocument();
});

describe("recurrence local start",()=>{it("rejects a spring-forward gap and chooses the earlier fall-overlap instant",()=>{expect(recurrenceStartInstant("2026-03-29T02:30","Europe/Budapest")).toBeNull();expect(recurrenceStartInstant("2026-10-25T02:30","Europe/Budapest")).toBe("2026-10-25T00:30:00.000Z")})});
