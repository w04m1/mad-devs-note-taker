# Final correctness work

## Frontend: manual DST fall-overlap selection

- **Decision:** Resolve a manually entered ordinary-note wall time in the profile IANA timezone. A spring-forward gap fails the wall-clock round trip and remains a field-level error. A fall-back overlap renders a named radio group with both chronological occurrences, their explicit UTC offsets, and their UTC clock times. Neither option is preselected. Save is blocked until the user chooses one, and the chosen offset-qualified instant is sent unchanged to the API.
- **Alternative considered:** Continue selecting the earlier occurrence automatically. This matches recurring-series generation, but it cannot express the user’s intent for a one-off note and violates the manual-entry rule. A browser-zone `Date` conversion was also rejected because the browser zone can differ from the saved profile zone.
- **Scope boundary:** Recurring schedules keep the frozen rule that ambiguous generated occurrences select the earlier instant. Calendar drag values already carry an offset and are not ambiguous manual wall-time input.
- **Evidence:** `note-form.test.tsx` covers the Budapest 2026 spring gap, both fall-overlap candidates, accessible group/radio names, no default selection, blocked submit, explicit second-occurrence selection, and the `+01:00` request payload. The full frontend suite passes (30 tests), as do TypeScript typecheck and production build. The build retains the known main-chunk warning (795.00 kB minified); this change adds no dependency.
