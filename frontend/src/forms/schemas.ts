import { z } from "zod";
const offsetDateTime=z.string().refine(value=>!Number.isNaN(Date.parse(value)) && /(Z|[+-]\d{2}:\d{2})$/.test(value),"Use a date and time with a UTC offset");
export const noteFormSchema=z.object({title:z.string().trim().min(1,"Title is required").max(200),body:z.string().max(10000),starts_at:offsetDateTime,active:z.boolean(),tag_ids:z.array(z.uuid()),reminder_offsets_minutes:z.array(z.union([z.literal(10),z.literal(60),z.literal(1440)])).refine(v=>new Set(v).size===v.length,"Choose each reminder once")});
export const tagFormSchema=z.object({name:z.string().trim().min(1).max(80),color:z.string().regex(/^#[0-9a-fA-F]{6}$/,"Use a six-digit hex color")});
export const settingsFormSchema=z.object({email:z.email(),timezone:z.string().min(1),expected_version:z.number().int().nonnegative()});
export const searchSchema=z.string().trim().refine(v=>v.length===0||v.length>=3,"Enter at least 3 characters");
export type NoteFormValues=z.infer<typeof noteFormSchema>;
