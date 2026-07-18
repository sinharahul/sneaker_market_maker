import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GuidedDemo } from "./GuidedDemo";
import { createDemoService } from "./demoService";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

beforeEach(() => {
  vi.useFakeTimers();
});

const BEATS = [
  "healthy_spread",
  "deterministic_bid",
  "paper_buy_fill",
  "shipping_authenticated",
  "inventory_ask_sale",
  "risk_gate_rejection",
];

function expectFrameFields(beat: string) {
  const panel = screen.getByRole("region", { name: "Guided demo frame" });
  expect(within(panel).getByText(beat)).toBeVisible();
  expect(within(panel).getByText(/Deterministic action:/)).toBeVisible();
  expect(within(panel).getByText(/PFHedge score:/)).toBeVisible();
  expect(within(panel).getByText(/IQL shadow action:/)).toBeVisible();
  expect(within(panel).getByText(/Final gated action:/)).toBeVisible();
  expect(within(panel).getByText(/Inventory lifecycle:/)).toBeVisible();
  expect(within(panel).getByText(/Cash:/)).toBeVisible();
  expect(within(panel).getByText(/NAV:/)).toBeVisible();
  expect(within(panel).getByText(/Realized P&L:/)).toBeVisible();
  expect(within(panel).getByText(/Unrealized P&L:/)).toBeVisible();
  expect(within(panel).getByText(/seller fee/i)).toBeVisible();
}

describe("GuidedDemo", () => {
  it("renders the first snapshot and accessible controls", () => {
    render(<GuidedDemo createService={createDemoService} />);

    expect(screen.getByRole("heading", { name: "Guided demo" })).toBeVisible();
    expect(screen.getByRole("status", { name: "Demo beat" })).toHaveTextContent(
      "healthy_spread",
    );
    expectFrameFields("healthy_spread");
    expect(screen.getByRole("button", { name: "Pause demo" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Resume demo" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Step demo forward" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Restart demo" })).toBeVisible();
  });

  it("steps exactly one beat per manual step", () => {
    render(<GuidedDemo createService={createDemoService} />);

    fireEvent.click(screen.getByRole("button", { name: "Step demo forward" }));
    expect(screen.getByRole("status", { name: "Demo beat" })).toHaveTextContent(
      "deterministic_bid",
    );

    fireEvent.click(screen.getByRole("button", { name: "Step demo forward" }));
    expect(screen.getByRole("status", { name: "Demo beat" })).toHaveTextContent(
      "paper_buy_fill",
    );
  });

  it("freezes on pause and advances on resume", () => {
    render(<GuidedDemo createService={createDemoService} beatIntervalMs={1000} />);

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "Resume demo" }));
    });
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByRole("status", { name: "Demo beat" })).toHaveTextContent(
      "deterministic_bid",
    );

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "Pause demo" }));
    });
    const frozenBeat = screen.getByRole("status", { name: "Demo beat" }).textContent;
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.getByRole("status", { name: "Demo beat" })).toHaveTextContent(
      frozenBeat ?? "",
    );

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "Resume demo" }));
    });
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByRole("status", { name: "Demo beat" })).toHaveTextContent(
      "paper_buy_fill",
    );
  });

  it("restart restores the first snapshot after playback", () => {
    render(<GuidedDemo createService={createDemoService} />);
    const initial = screen.getByRole("status", { name: "Demo beat" }).textContent;

    for (let index = 0; index < 3; index += 1) {
      fireEvent.click(screen.getByRole("button", { name: "Step demo forward" }));
    }
    expect(screen.getByRole("status", { name: "Demo beat" })).not.toHaveTextContent(
      initial ?? "",
    );

    fireEvent.click(screen.getByRole("button", { name: "Restart demo" }));
    expect(screen.getByRole("status", { name: "Demo beat" })).toHaveTextContent(
      initial ?? "",
    );
    expectFrameFields("healthy_spread");
  });

  it("walks through every pinned beat without fetch", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(() => {
      throw new Error("fetch must not be called");
    });

    render(<GuidedDemo createService={createDemoService} />);
    for (const beat of BEATS) {
      expect(screen.getByRole("status", { name: "Demo beat" })).toHaveTextContent(beat);
      expectFrameFields(beat);
      if (beat !== BEATS[BEATS.length - 1]) {
        fireEvent.click(screen.getByRole("button", { name: "Step demo forward" }));
      }
    }

    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
