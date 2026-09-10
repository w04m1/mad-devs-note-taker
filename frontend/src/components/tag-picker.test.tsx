import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Tag } from "../api/contracts";
import { TagPicker } from "./tag-picker";

const tags: Tag[] = Array.from({ length: 50 }, (_, index) => ({
  id: `tag-${index + 1}`,
  name: `Project ${String(index + 1).padStart(2, "0")}`,
  color: index % 2 ? "#2563eb" : "#dc2626",
  version: 1,
}));

function Harness() {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  return (
    <TagPicker
      label="Filter by tags"
      tags={tags}
      selectedIds={selectedIds}
      onToggle={(id) =>
        setSelectedIds((current) =>
          current.includes(id)
            ? current.filter((tagId) => tagId !== id)
            : [...current, id],
        )
      }
    />
  );
}

describe("TagPicker", () => {
  it("keeps a large tag collection searchable and summarizes selections", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(
      screen.getByRole("button", { name: "Filter by tags: Choose tags" }),
    );
    expect(screen.getByText("0 of 50 selected")).toBeInTheDocument();

    await user.type(screen.getByRole("textbox", { name: "Search tags" }), "47");
    expect(screen.getByText("Project 47")).toBeInTheDocument();
    expect(screen.queryByText("Project 01")).not.toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: "Project 47" }));
    expect(screen.getByText("1 of 50 selected")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Filter by tags: Project 47" }),
    ).toBeInTheDocument();
  });
});
