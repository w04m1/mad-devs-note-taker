import { useState } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { DateTimePicker } from "./date-time-picker";

afterEach(cleanup);

function Harness({ clearable = false }: { clearable?: boolean }) {
  const [value, setValue] = useState("2026-09-18T11:30");
  return (
    <DateTimePicker
      label="Appointment"
      value={value}
      onChange={setValue}
      clearable={clearable}
    />
  );
}

describe("date-time picker", () => {
  it("changes the calendar date while preserving the selected time", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("button", { name: "Appointment" }));
    await user.click(
      screen.getByRole("button", {
        name: "Saturday, September 19th, 2026",
      }),
    );

    expect(screen.getByRole("button", { name: "Appointment" })).toHaveTextContent(
      "September 19th, 2026 · 11:30",
    );
  });

  it("clears optional values from the popover", async () => {
    const user = userEvent.setup();
    render(<Harness clearable />);

    await user.click(screen.getByRole("button", { name: "Appointment" }));
    await user.click(screen.getByRole("button", { name: "Clear" }));

    expect(screen.getByRole("button", { name: "Appointment" })).toHaveTextContent(
      "Choose date and time",
    );
  });
});
