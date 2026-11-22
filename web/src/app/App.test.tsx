import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import fixture from "../test/report.fixture.json";
import { App } from "./App";

afterEach(() => vi.restoreAllMocks());

function serve(status: number, body?: unknown) {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(body ? JSON.stringify(body) : null, { status }));
}

describe("dashboard", () => {
  it("shows the headline, the matrix and the failing cell's detail", async () => {
    serve(200, fixture);
    render(<App />);
    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("real SDK runs"));
    const failing = screen.getAllByRole("button", { name: /1 generation \/ call fails/ });
    expect(failing.length).toBeGreaterThan(0);
    fireEvent.click(failing[0]!);
    expect(screen.getAllByText(/generations for 2 calls/).length).toBeGreaterThan(0);
    expect(screen.getByText("The first release that broke it")).toBeInTheDocument();
  });

  it("says how to make a missing report", async () => {
    serve(404);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/python -m gtc.eval.cli heldout/)).toBeInTheDocument());
  });

  it("offers a retry when the report fails", async () => {
    serve(500);
    render(<App />);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("HTTP 500"));
  });
});
