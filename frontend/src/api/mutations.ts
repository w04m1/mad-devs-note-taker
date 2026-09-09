import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { NoteUpdate, NoteWrite, SettingsUpdate, TagWrite } from "./contracts";
import { queryKeys } from "./query-keys";

/** Shared mutation policy: update authoritative caches only after success. Failed/conflicting writes keep form state intact. */
export function useNoteMutations() {
  const client = useQueryClient();
  const refresh = () => Promise.all([
    client.invalidateQueries({ queryKey: queryKeys.notes.all }),
    client.invalidateQueries({ queryKey: queryKeys.calendar.all }),
    client.invalidateQueries({ queryKey: queryKeys.upcoming.all }),
    client.invalidateQueries({ queryKey: queryKeys.trash.all }),
  ]);
  const create = useMutation({ mutationFn: (value: NoteWrite) => api.notes.create(value), onSuccess: refresh });
  const update = useMutation({ mutationFn: ({ id, value }: { id: string; value: NoteUpdate }) => api.notes.update(id, value), onSuccess: refresh });
  const remove = useMutation({ mutationFn: ({ id, version, seriesVersion }: { id: string; version: number; seriesVersion?: number }) => api.notes.remove(id, version, seriesVersion), onSuccess: refresh });
  const restore = useMutation({ mutationFn: ({ id, version, seriesVersion }: { id: string; version: number; seriesVersion?: number }) => api.notes.restore(id, version, seriesVersion), onSuccess: refresh });
  return { create, update, remove, restore };
}

export function useTagMutations() {
  const client = useQueryClient();
  const refresh = () => Promise.all([client.invalidateQueries({ queryKey: queryKeys.tags.all }), client.invalidateQueries({ queryKey: queryKeys.notes.all })]);
  return {
    create: useMutation({ mutationFn: (value: TagWrite) => api.tags.create(value), onSuccess: refresh }),
    update: useMutation({ mutationFn: ({ id, value }: { id: string; value: TagWrite & { expected_version: number } }) => api.tags.update(id, value), onSuccess: refresh }),
    remove: useMutation({ mutationFn: ({ id, version }: { id: string; version: number }) => api.tags.remove(id, version), onSuccess: refresh }),
  };
}

export function useSettingsMutation() {
  const client = useQueryClient();
  return useMutation({ mutationFn: (value: SettingsUpdate) => api.settings.update(value), onSuccess: value => {
    client.setQueryData(queryKeys.settings.all, value);
    void client.invalidateQueries({ queryKey: queryKeys.notes.all });
    void client.invalidateQueries({ queryKey: queryKeys.calendar.all });
    void client.invalidateQueries({ queryKey: queryKeys.upcoming.all });
  } });
}
