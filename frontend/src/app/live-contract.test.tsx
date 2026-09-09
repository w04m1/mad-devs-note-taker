import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { App } from "./app";
import { ToastProvider } from "../components/toast";

class QuietSocket { onopen:null|(()=>void)=null; onmessage=null; onclose=null; constructor(){queueMicrotask(()=>this.onopen?.())} close(){} }
const emptyPage={items:[],total:0,page:1,page_size:50};
function responseFor(url:string, malformedTags=false){
  if(url.includes("/settings"))return {email:"demo@example.test",timezone:"UTC",version:1};
  if(url.includes("/tags"))return malformedTags?{items:[]}:[];
  if(url.includes("/notes"))return emptyPage;
  throw new Error(`Unexpected request ${url}`);
}
function mount(malformedTags=false){
  vi.stubGlobal("WebSocket",QuietSocket);
  vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL)=>new Response(JSON.stringify(responseFor(String(input),malformedTags)),{status:200,headers:{"content-type":"application/json"}})));
  const client=new QueryClient({defaultOptions:{queries:{retry:false}}});
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/notes"]}><ToastProvider><App/></ToastProvider></MemoryRouter></QueryClientProvider>);
}
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks()});

describe("live HTTP shape integration",()=>{
  it("renders Notes with the GET /tags array and paged GET /notes contracts",async()=>{
    mount();
    expect(await screen.findByText("No matching notes.")).toBeInTheDocument();
    expect(screen.getByRole("navigation",{name:"Main navigation"})).toBeInTheDocument();
  });
  it("keeps the shell available if a malformed response crashes a screen",async()=>{
    vi.spyOn(console,"error").mockImplementation(()=>undefined);
    mount(true);
    expect(await screen.findByText("This page could not be displayed.")).toBeInTheDocument();
    expect(screen.getByRole("navigation",{name:"Main navigation"})).toBeInTheDocument();
    await waitFor(()=>expect(screen.getByRole("button",{name:"Reload page"})).toBeInTheDocument());
  });
});
