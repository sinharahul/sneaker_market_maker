import React from "react";
import ReactDOM from "react-dom/client";

import { GuidedDemo } from "./research/GuidedDemo";
import { ResearchPageLoader } from "./research/ResearchPage";
import "./demo.css";

const root = document.getElementById("root");
if (root === null) {
  throw new Error("Missing application root");
}

const showResearch =
  new URLSearchParams(window.location.search).get("view") === "research";

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    {showResearch ? <ResearchPageLoader /> : <GuidedDemo />}
  </React.StrictMode>,
);
