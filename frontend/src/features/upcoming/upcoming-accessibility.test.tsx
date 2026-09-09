import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { Note, UpcomingResponse } from "../../api/contracts";

const upcomingMock = vi.hoisted(() => vi.fn());
const note: Note = { id: "n1", title: "Accessible meeting", body: "", starts_at: "2026-01-01T10:00:00Z", active: true, tags: [], reminder_offsets_minutes: [], version: 1, created_at: "", updated_at: "", deleted_at: null, series_id: null, recurrence_key: null };
const response: UpcomingResponse = { today: {items:[note],total:1,page:1,page_size:50}, week: {items:[],total:0,page:1,page_size:50}, past: {items:[],total:0,page:1,page_size:50}, server_now: "2026-01-01T09:00:00Z", next_transition_at: "2026-01-01T10:00:00Z" };
vi.mock("../../api/client", async original => {
  const actual = await original<typeof import("../../api/client")>();
  return { ...actual, api: { ...actual.api, upcoming: upcomingMock } };
});
import { UpcomingView } from "./upcoming-view";

describe("Upcoming accessibility", () => {
  it("labels each mutually exclusive group and opens a note with a native button", async () => {
    upcomingMock.mockResolvedValue(response);
    const onOpen = vi.fn();
    render(<QueryClientProvider client={new QueryClient()}><UpcomingView timezone="UTC" onOpen={onOpen} /></QueryClientProvider>);
    expect(await screen.findByRole("heading", { name: "Today (1)" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "This week (0)" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Past active (0)" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Accessible meeting/ }));
    expect(onOpen).toHaveBeenCalledWith(note);
  });
});
