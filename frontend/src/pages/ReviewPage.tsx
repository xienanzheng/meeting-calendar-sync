import { Link } from "react-router";
import { Shell } from "../components/Shell";

// Placeholder: Task 11 replaces this with the "By colleague" review surface.
export function ReviewPage() {
  return (
    <Shell>
      <div className="mx-auto max-w-[1100px] px-7 pb-16 pt-9">
        <p className="text-[15px] font-medium text-muted">Review coming in the next task.</p>
        <Link to="/" className="mt-3 inline-block rounded-sm text-sm font-semibold text-blue underline">
          Back to conferences
        </Link>
      </div>
    </Shell>
  );
}
