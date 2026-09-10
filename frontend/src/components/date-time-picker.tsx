import { useState } from "react";
import { format } from "date-fns";
import { CalendarDays, Clock3, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

type DateTimePickerProps = {
  value: string;
  onChange: (value: string) => void;
  label: string;
  mode?: "date" | "datetime";
  placeholder?: string;
  defaultTime?: string;
  clearable?: boolean;
  disabled?: boolean;
  className?: string;
};

const hours = Array.from({ length: 24 }, (_, hour) =>
  String(hour).padStart(2, "0"),
);
const minutes = Array.from({ length: 60 }, (_, minute) =>
  String(minute).padStart(2, "0"),
);

function parts(value: string, defaultTime: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?$/.exec(value);
  const [fallbackHour = "09", fallbackMinute = "00"] = defaultTime.split(":");
  if (!match)
    return {
      date: undefined,
      hour: fallbackHour,
      minute: fallbackMinute,
    };
  const date = new Date(
    Number(match[1]),
    Number(match[2]) - 1,
    Number(match[3]),
  );
  return {
    date: Number.isNaN(date.getTime()) ? undefined : date,
    hour: match[4] ?? fallbackHour,
    minute: match[5] ?? fallbackMinute,
  };
}

export function DateTimePicker({
  value,
  onChange,
  label,
  mode = "datetime",
  placeholder = mode === "date" ? "Choose a date" : "Choose date and time",
  defaultTime = "09:00",
  clearable = false,
  disabled = false,
  className,
}: DateTimePickerProps) {
  const [open, setOpen] = useState(false);
  const selected = parts(value, defaultTime);
  const commit = (date: Date, hour = selected.hour, minute = selected.minute) =>
    onChange(
      mode === "date"
        ? format(date, "yyyy-MM-dd")
        : `${format(date, "yyyy-MM-dd")}T${hour}:${minute}`,
    );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          aria-label={label}
          aria-expanded={open}
          disabled={disabled}
          className={cn(
            "w-full min-w-0 justify-start px-3 font-normal",
            !value && "text-muted-foreground",
            className,
          )}
        >
          <CalendarDays data-icon="inline-start" />
          <span className="min-w-0 flex-1 truncate text-left">
            {selected.date
              ? mode === "date"
                ? format(selected.date, "PPP")
                : `${format(selected.date, "PPP")} · ${selected.hour}:${selected.minute}`
              : placeholder}
          </span>
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="w-[19rem] max-w-[calc(100vw-2rem)] overflow-hidden p-0"
      >
        <Calendar
          mode="single"
          className="[--cell-size:2.25rem]"
          classNames={{ root: "w-full" }}
          {...(selected.date
            ? { selected: selected.date, defaultMonth: selected.date }
            : {})}
          onSelect={(date) => {
            if (date) commit(date);
          }}
        />
        {mode === "datetime" && (
          <div className="flex items-end gap-2 border-t p-3">
            <Clock3 className="mb-2.5 text-muted-foreground" aria-hidden />
            <label className="flex min-w-0 flex-1 flex-col gap-1.5 text-xs font-medium">
              Hour
              <Select
                value={selected.hour}
                disabled={!selected.date}
                onValueChange={(hour) => {
                  if (selected.date)
                    commit(selected.date, hour, selected.minute);
                }}
              >
                <SelectTrigger aria-label={`${label} hour`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {hours.map((hour) => (
                      <SelectItem key={hour} value={hour}>
                        {hour}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </label>
            <span className="pb-2.5 text-muted-foreground">:</span>
            <label className="flex min-w-0 flex-1 flex-col gap-1.5 text-xs font-medium">
              Minute
              <Select
                value={selected.minute}
                disabled={!selected.date}
                onValueChange={(minute) => {
                  if (selected.date)
                    commit(selected.date, selected.hour, minute);
                }}
              >
                <SelectTrigger aria-label={`${label} minute`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {minutes.map((minute) => (
                      <SelectItem key={minute} value={minute}>
                        {minute}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </label>
          </div>
        )}
        <div className="flex justify-end gap-2 border-t p-3">
          {clearable && value && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                onChange("");
                setOpen(false);
              }}
            >
              <X data-icon="inline-start" />
              Clear
            </Button>
          )}
          <Button type="button" size="sm" onClick={() => setOpen(false)}>
            Done
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
