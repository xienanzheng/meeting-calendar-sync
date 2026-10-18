import { CircleAlert, RotateCw, X } from "lucide-react";
import { Button } from "./Button";

/** Inline red note: what went wrong, the server's message, and an optional retry. */
export function ErrorNote({
  title,
  message,
  onRetry,
  retryLabel = "Try again",
  onDismiss,
}: {
  title: string;
  message?: string;
  onRetry?: () => void;
  retryLabel?: string;
  onDismiss?: () => void;
}) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-md border border-red-line bg-red-bg px-4 py-3 text-sm text-red">
      <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="font-bold">{title}</p>
        {message && <p className="mt-0.5 font-medium [overflow-wrap:anywhere]">{message}</p>}
      </div>
      {onRetry && (
        <Button size="sm" onClick={onRetry} icon={<RotateCw className="size-3.5" aria-hidden="true" />}>
          {retryLabel}
        </Button>
      )}
      {onDismiss && (
        <Button
          size="icon"
          variant="quiet"
          onClick={onDismiss}
          aria-label="Dismiss"
          className="-my-1 -mr-1.5 border-transparent bg-transparent text-red enabled:hover:bg-white"
          icon={<X className="size-4" aria-hidden="true" />}
        />
      )}
    </div>
  );
}
