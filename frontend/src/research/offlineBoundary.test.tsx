import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GuidedDemo } from "./GuidedDemo";
import { createDemoService } from "./demoService";

const BEATS = [
  "healthy_spread",
  "deterministic_bid",
  "paper_buy_fill",
  "shipping_authenticated",
  "inventory_ask_sale",
  "risk_gate_rejection",
];

afterEach(() => {
  cleanup();
});

describe("offline research boundary", () => {
  it("completes GuidedDemo from injected fixtures when fetch is denied", () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => {
      throw new Error("network denied");
    });

    render(<GuidedDemo createService={createDemoService} />);

    for (const beat of BEATS) {
      expect(screen.getByRole("status", { name: "Demo beat" })).toHaveTextContent(beat);
      if (beat !== BEATS[BEATS.length - 1]) {
        fireEvent.click(screen.getByRole("button", { name: "Step demo forward" }));
      }
    }

    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
