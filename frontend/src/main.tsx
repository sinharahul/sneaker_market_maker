import React from "react";
import ReactDOM from "react-dom/client";

import { ResearchPageLoader } from "./research/ResearchPage";

const root = document.getElementById("root");
if (root === null) {
  throw new Error("Missing application root");
}

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <ResearchPageLoader />
  </React.StrictMode>,
);
