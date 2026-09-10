import { useMemo, useState } from "react";
import { Check, ChevronDown, Search, Tags as TagsIcon, X } from "lucide-react";

import type { Tag } from "../api/contracts";
import { Button } from "./ui/button";
import { Checkbox } from "./ui/checkbox";
import { Input } from "./ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";

export function TagPicker({
  tags,
  selectedIds,
  onToggle,
  label = "Tags",
}: {
  tags: Tag[];
  selectedIds: string[];
  onToggle: (id: string) => void;
  label?: string;
}) {
  const [query, setQuery] = useState("");
  const safeTags = Array.isArray(tags) ? tags : [];
  const selected = useMemo(
    () => safeTags.filter((tag) => selectedIds.includes(tag.id)),
    [selectedIds, safeTags],
  );
  const visibleTags = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return normalized
      ? safeTags.filter((tag) =>
          tag.name.toLocaleLowerCase().includes(normalized),
        )
      : safeTags;
  }, [query, safeTags]);
  const summary =
    selected.length === 0
      ? "Choose tags"
      : selected.length <= 2
        ? selected.map((tag) => tag.name).join(", ")
        : `${selected.length} tags selected`;

  return (
    <Popover onOpenChange={(open) => !open && setQuery("")}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          className="w-full min-w-0 justify-between px-3 font-normal"
          aria-label={`${label}: ${summary}`}
        >
          <span className="flex min-w-0 items-center gap-2">
            <TagsIcon data-icon="inline-start" />
            <span className="truncate">{summary}</span>
          </span>
          <ChevronDown
            data-icon="inline-end"
            className="text-muted-foreground"
          />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="w-80 max-w-[calc(100vw-2rem)] p-0"
      >
        <div className="border-b p-3">
          <div className="relative">
            <Search
              aria-hidden
              className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search tags…"
              aria-label="Search tags"
              className="pl-9"
            />
          </div>
        </div>
        <div
          className="max-h-64 overflow-y-auto overscroll-contain p-2"
          role="group"
          aria-label={`${label} options`}
        >
          {visibleTags.length ? (
            visibleTags.map((tag) => {
              const checked = selectedIds.includes(tag.id);
              return (
                <label
                  key={tag.id}
                  className="flex min-h-10 cursor-pointer items-center gap-3 rounded-md px-2.5 py-2 text-sm hover:bg-accent"
                >
                  <Checkbox
                    checked={checked}
                    onCheckedChange={() => onToggle(tag.id)}
                    aria-label={tag.name}
                  />
                  <span
                    className="size-2.5 shrink-0 rounded-full ring-1 ring-black/10"
                    style={{ backgroundColor: tag.color }}
                  />
                  <span className="min-w-0 flex-1 truncate">{tag.name}</span>
                  {checked && (
                    <Check aria-hidden className="size-4 shrink-0 text-primary" />
                  )}
                </label>
              );
            })
          ) : (
            <p className="px-3 py-8 text-center text-sm text-muted-foreground">
              {safeTags.length ? "No tags match your search." : "No tags yet."}
            </p>
          )}
        </div>
        <div className="flex items-center justify-between gap-3 border-t px-3 py-2">
          <span className="text-xs text-muted-foreground">
            {selected.length} of {safeTags.length} selected
          </span>
          {selected.length > 0 && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => selected.forEach((tag) => onToggle(tag.id))}
            >
              <X data-icon="inline-start" />
              Clear
            </Button>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
