import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ConfirmDialog from "./ConfirmDialog";

const baseProps = {
  title: "Title",
  confirmLabel: "OK",
  cancelLabel: "Cancel",
  onCancel: () => {},
};

afterEach(() => {
  cleanup();
});

describe("ConfirmDialog", () => {
  it("renders nothing while closed", () => {
    const { container } = render(
      <ConfirmDialog {...baseProps} open={false} onConfirm={() => {}} />,
    );
    expect(container.innerHTML).toBe("");
  });

  it("reports the do-not-show-again checkbox on confirm", () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog
        {...baseProps}
        open
        doNotShowAgainLabel="Hide"
        onConfirm={onConfirm}
      >
        body
      </ConfirmDialog>,
    );
    fireEvent.click(screen.getByLabelText("Hide"));
    fireEvent.click(screen.getByText("OK"));
    expect(onConfirm).toHaveBeenCalledWith({ doNotShowAgain: true });
  });

  it("disables both buttons while busy and ignores overlay clicks", () => {
    const onCancel = vi.fn();
    render(
      <ConfirmDialog
        {...baseProps}
        open
        busy
        dismissible
        onConfirm={() => {}}
        onCancel={onCancel}
      />,
    );
    expect((screen.getByText("OK") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByText("Cancel") as HTMLButtonElement).disabled).toBe(
      true,
    );
    fireEvent.click(screen.getByRole("dialog"));
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("cancels on overlay click and Escape only when dismissible", () => {
    const onCancel = vi.fn();
    const { rerender } = render(
      <ConfirmDialog
        {...baseProps}
        open
        onConfirm={() => {}}
        onCancel={onCancel}
      />,
    );
    fireEvent.click(screen.getByRole("dialog"));
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onCancel).not.toHaveBeenCalled();

    rerender(
      <ConfirmDialog
        {...baseProps}
        open
        dismissible
        onConfirm={() => {}}
        onCancel={onCancel}
      />,
    );
    fireEvent.click(screen.getByRole("dialog"));
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onCancel).toHaveBeenCalledTimes(2);
  });

  it("keeps the confirm button disabled via confirmDisabled", () => {
    render(
      <ConfirmDialog
        {...baseProps}
        open
        confirmDisabled
        onConfirm={() => {}}
      />,
    );
    expect((screen.getByText("OK") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByText("Cancel") as HTMLButtonElement).disabled).toBe(
      false,
    );
  });
});
