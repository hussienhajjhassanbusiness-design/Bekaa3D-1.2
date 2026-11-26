import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MfaSetupPage from "./page";
import { useMfaSetup } from "@/lib/auth/useMfaSetup";
import { useMfaSetupConfirm } from "@/lib/auth/useMfaSetupConfirm";

// Phase 3 (FVS-005/P1-2) — MFA enrolment for an admin whose enrolment is
// incomplete (reached via AdminGuard's mfaRequiredSignal redirect, or
// directly). secret/otpauth_uri are sensitive and memory-only — never
// rendered via a persisted/loggable mechanism, never sent anywhere but
// shown once on screen. Recovery codes (step 3) require an explicit
// "I've saved these" acknowledgment before the admin can continue —
// they are shown exactly once.
vi.mock("@/lib/auth/useMfaSetup", () => ({ useMfaSetup: vi.fn() }));
vi.mock("@/lib/auth/useMfaSetupConfirm", () => ({ useMfaSetupConfirm: vi.fn() }));
const mockedUseMfaSetup = vi.mocked(useMfaSetup);
const mockedUseMfaSetupConfirm = vi.mocked(useMfaSetupConfirm);

const mockReplace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace }),
}));

function httpError(status: number, code: string) {
  return { kind: "http" as const, status, code, message: "x", raw: undefined };
}

const SETUP_RESPONSE = {
  secret: "ABCD1234SECRET",
  otpauth_uri: "otpauth://totp/Bekaa3D:admin@example.com?secret=ABCD1234SECRET&issuer=Bekaa3D",
  issuer: "Bekaa3D",
  account_name: "admin@example.com",
};

const RECOVERY_RESPONSE = {
  recovery_codes: ["aaaa-bbbb", "cccc-dddd"],
  generated_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  mockReplace.mockReset();
  mockedUseMfaSetup.mockReset();
  mockedUseMfaSetupConfirm.mockReset();
});

async function beginSetup(user: ReturnType<typeof userEvent.setup>, setupMutateAsync = vi.fn().mockResolvedValue(SETUP_RESPONSE)) {
  mockedUseMfaSetup.mockReturnValue({ mutateAsync: setupMutateAsync } as never);
  render(<MfaSetupPage />);
  await user.type(screen.getByLabelText(/current password/i), "hunter2");
  await user.click(screen.getByRole("button", { name: /begin setup/i }));
  await screen.findByLabelText(/verification code/i);
  return setupMutateAsync;
}

describe("MfaSetupPage", () => {
  it("step 1: renders a current-password field and begin-setup button", () => {
    mockedUseMfaSetup.mockReturnValue({ mutateAsync: vi.fn() } as never);
    mockedUseMfaSetupConfirm.mockReturnValue({ mutateAsync: vi.fn() } as never);
    render(<MfaSetupPage />);

    expect(screen.getByLabelText(/current password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /begin setup/i })).toBeInTheDocument();
  });

  it("step 1 -> step 2: submitting the password calls useMfaSetup and shows the secret, otpauth URI, and a code field", async () => {
    const user = userEvent.setup();
    mockedUseMfaSetupConfirm.mockReturnValue({ mutateAsync: vi.fn() } as never);
    const setupMutateAsync = await beginSetup(user);

    expect(setupMutateAsync).toHaveBeenCalledWith({ current_password: "hunter2" });
    expect(screen.getByText(/ABCD1234SECRET/)).toBeInTheDocument();
    expect(screen.getByText(/otpauth:\/\/totp/)).toBeInTheDocument();
  });

  it("step 1 error: INVALID_CREDENTIALS shows a safe message and stays on step 1", async () => {
    const user = userEvent.setup();
    const setupMutateAsync = vi.fn().mockRejectedValue(httpError(401, "INVALID_CREDENTIALS"));
    mockedUseMfaSetup.mockReturnValue({ mutateAsync: setupMutateAsync } as never);
    mockedUseMfaSetupConfirm.mockReturnValue({ mutateAsync: vi.fn() } as never);
    render(<MfaSetupPage />);


    await user.type(screen.getByLabelText(/current password/i), "wrong");
    await user.click(screen.getByRole("button", { name: /begin setup/i }));

    await screen.findByRole("alert");
    expect(screen.getByLabelText(/current password/i)).toBeInTheDocument();
  });

  it("step 1 error: 409 INVALID_STATE_TRANSITION (already enrolled) shows a safe message", async () => {
    const user = userEvent.setup();
    const setupMutateAsync = vi.fn().mockRejectedValue(httpError(409, "INVALID_STATE_TRANSITION"));
    mockedUseMfaSetup.mockReturnValue({ mutateAsync: setupMutateAsync } as never);
    mockedUseMfaSetupConfirm.mockReturnValue({ mutateAsync: vi.fn() } as never);
    render(<MfaSetupPage />);

    await user.type(screen.getByLabelText(/current password/i), "hunter2");
    await user.click(screen.getByRole("button", { name: /begin setup/i }));

    expect(await screen.findByText(/already (set up|enabled)/i)).toBeInTheDocument();
  });

  it("step 2 -> step 3: confirming the code calls useMfaSetupConfirm and shows the recovery codes", async () => {
    const user = userEvent.setup();
    const confirmMutateAsync = vi.fn().mockResolvedValue(RECOVERY_RESPONSE);
    mockedUseMfaSetupConfirm.mockReturnValue({ mutateAsync: confirmMutateAsync } as never);
    await beginSetup(user);

    await user.type(screen.getByLabelText(/verification code/i), "123456");
    await user.click(screen.getByRole("button", { name: /confirm/i }));

    expect(confirmMutateAsync).toHaveBeenCalledWith({ code: "123456" });
    expect(await screen.findByText("aaaa-bbbb")).toBeInTheDocument();
    expect(screen.getByText("cccc-dddd")).toBeInTheDocument();
  });

  it("step 2 error: 422 MFA_INVALID shows a safe message and stays on step 2 (no secret regenerated)", async () => {
    const user = userEvent.setup();
    const confirmMutateAsync = vi.fn().mockRejectedValue(httpError(422, "MFA_INVALID"));
    mockedUseMfaSetupConfirm.mockReturnValue({ mutateAsync: confirmMutateAsync } as never);
    await beginSetup(user);

    await user.type(screen.getByLabelText(/verification code/i), "000000");
    await user.click(screen.getByRole("button", { name: /confirm/i }));

    await screen.findByRole("alert");
    expect(screen.getByLabelText(/verification code/i)).toBeInTheDocument();
  });

  it("step 3: the continue button is disabled until the admin acknowledges saving the codes, then navigates to /admin", async () => {
    const user = userEvent.setup();
    const confirmMutateAsync = vi.fn().mockResolvedValue(RECOVERY_RESPONSE);
    mockedUseMfaSetupConfirm.mockReturnValue({ mutateAsync: confirmMutateAsync } as never);
    await beginSetup(user);
    await user.type(screen.getByLabelText(/verification code/i), "123456");
    await user.click(screen.getByRole("button", { name: /confirm/i }));
    await screen.findByText("aaaa-bbbb");

    const continueButton = screen.getByRole("button", { name: /continue/i });
    expect(continueButton).toBeDisabled();

    await user.click(screen.getByRole("checkbox", { name: /saved these/i }));
    expect(continueButton).toBeEnabled();

    await user.click(continueButton);
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/admin"));
  });

  it("never renders the secret or otpauth URI once past step 2 (recovery-codes step)", async () => {
    const user = userEvent.setup();
    const confirmMutateAsync = vi.fn().mockResolvedValue(RECOVERY_RESPONSE);
    mockedUseMfaSetupConfirm.mockReturnValue({ mutateAsync: confirmMutateAsync } as never);
    await beginSetup(user);
    await user.type(screen.getByLabelText(/verification code/i), "123456");
    await user.click(screen.getByRole("button", { name: /confirm/i }));
    await screen.findByText("aaaa-bbbb");

    expect(screen.queryByText(/ABCD1234SECRET/)).toBeNull();
  });
});
