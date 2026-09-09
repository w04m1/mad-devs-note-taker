import * as DialogPrimitive from "@radix-ui/react-dialog";
import type { ComponentProps, ReactNode } from "react";

export function Dialog(props: ComponentProps<typeof DialogPrimitive.Root> & { trigger?: ReactNode; title?: string; description?: string }) {
  const {trigger,title,description,children,...root}=props;
  if(trigger!==undefined&&title!==undefined)return <DialogPrimitive.Root {...root}><DialogPrimitive.Trigger asChild>{trigger}</DialogPrimitive.Trigger><DialogContent><DialogTitle>{title}</DialogTitle>{description&&<DialogDescription>{description}</DialogDescription>}<div className="mt-4">{children}</div></DialogContent></DialogPrimitive.Root>;
  return <DialogPrimitive.Root {...root}>{children}</DialogPrimitive.Root>;
}
export function DialogContent({children,...props}:ComponentProps<typeof DialogPrimitive.Content>){return <DialogPrimitive.Portal><DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/40"/><DialogPrimitive.Content {...props} className={`fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[min(36rem,calc(100%-2rem))] -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-lg bg-white p-6 shadow-xl ${props.className??""}`}><DialogPrimitive.Close aria-label="Close dialog" className="absolute right-4 top-4 text-xl">×</DialogPrimitive.Close>{children}</DialogPrimitive.Content></DialogPrimitive.Portal>}
export function DialogTitle(props:ComponentProps<typeof DialogPrimitive.Title>){return <DialogPrimitive.Title {...props} className={`text-lg font-bold ${props.className??""}`}/>}
export function DialogDescription(props:ComponentProps<typeof DialogPrimitive.Description>){return <DialogPrimitive.Description {...props} className={`mt-1 mb-4 text-sm text-slate-600 ${props.className??""}`}/>}
