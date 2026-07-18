import React from "react";
import ReactDOM from "react-dom/client";

import { OpsDashboard } from "./ops/OpsDashboard";
import { GuidedDemo } from "./research/GuidedDemo";
import { ResearchPageLoader } from "./research/ResearchPage";
import "./demo.css";

const root = document.getElementById("root");
if (root === null) {
  throw new Error("Missing application root");
}

const view = new URLSearchParams(window.location.search).get("view");

function App(): JSX.Element {
  if (view === "research") {
    return <ResearchPageLoader />;
  }
  if (view === "ops") {
    return <OpsDashboard />;
  }
  return <GuidedDemo />;
}

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
