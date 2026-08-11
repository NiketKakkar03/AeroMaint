import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App.js";
import { createSyntheticViewerDataSource } from "./lib/syntheticFixture.js";
import "./styles.css";

const root = document.querySelector<HTMLDivElement>("#root");

if (root === null) {
  throw new Error("Viewer root element was not found");
}

const queryClient = new QueryClient();
const fixtureMode = new URLSearchParams(window.location.search).get("fixture");
const requestedSamples = Number(
  new URLSearchParams(window.location.search).get("sensorSamples") ?? "64"
);
const fixtureDataSource = fixtureMode
  ? createSyntheticViewerDataSource(
      fixtureMode === "webcodecs",
      Number.isInteger(requestedSamples) && requestedSamples > 0
        ? requestedSamples
        : 64
    )
  : undefined;

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App {...(fixtureDataSource ? { dataSource: fixtureDataSource } : {})} />
    </QueryClientProvider>
  </StrictMode>
);
