import { Component, type ErrorInfo, type ReactNode } from "react";
import { CircleAlert, RotateCcw } from "lucide-react";
import { Button } from "../components/ui/button";

export class ScreenErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Screen render failed", error, info);
  }
  render() {
    return this.state.failed ? (
      <section
        role="alert"
        className="rounded-2xl border border-destructive/20 bg-card p-6 shadow-sm"
      >
        <div className="flex items-start gap-4">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-destructive/10 text-destructive">
            <CircleAlert />
          </span>
          <div>
            <h1 className="text-xl font-semibold">
              This page could not be displayed.
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              The application shell is still available. Reload after the server
              response is corrected.
            </p>
          </div>
        </div>
        <Button className="mt-5" onClick={() => location.reload()}>
          <RotateCcw data-icon="inline-start" />
          Reload page
        </Button>
      </section>
    ) : (
      this.props.children
    );
  }
}
