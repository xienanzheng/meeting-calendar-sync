import { BrowserRouter, Link, Route, Routes } from "react-router";
import { Shell } from "./components/Shell";
import { ConferencesPage } from "./pages/ConferencesPage";
import { ReviewPage } from "./pages/ReviewPage";
import { RosterPage } from "./pages/RosterPage";

function NotFound() {
  return (
    <Shell>
      <div className="mx-auto max-w-[1100px] px-7 pb-16 pt-9">
        <h1 className="text-[28px] font-bold leading-tight text-navy">Page not found</h1>
        <p className="mt-1.5 text-[15px] text-muted">
          There's nothing at this address.{" "}
          <Link to="/" className="rounded-sm font-semibold text-blue underline">
            Go to conferences
          </Link>
          .
        </p>
      </div>
    </Shell>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ConferencesPage />} />
        <Route path="/conferences/:id" element={<ReviewPage />} />
        <Route path="/roster" element={<RosterPage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  );
}
