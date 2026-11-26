// FVS-003-IMPLEMENTATION-PLAN.md §2 rows 2/5/5b/6/8/9/9b (confirmed BATCH
// 3B) — the login mutation. Two disjoint success shapes exist (a normal
// `200` session vs. a `202` MFA challenge, which establishes NO session and
// sets NO cookies) — discriminated by body shape (`user_id` vs
// `challenge_id`), never by trusting "any 2xx." Calls `apiClient` directly,
// never `authenticatedRequest` — login must never trigger a refresh on
// failure (§6's exclusion rule).
import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginSessionBody {
  user_id: string;
  email: string;
  role: string;
  email_verified: boolean;
  session_expires_at: string;
}

export interface LoginMfaChallengeBody {
  challenge_id: string;
  expires_in_seconds: number;
}

export type LoginResult =
  | { kind: "session"; data: LoginSessionBody }
  | { kind: "mfaChallenge"; data: LoginMfaChallengeBody };

function isMfaChallengeBody(body: unknown): body is LoginMfaChallengeBody {
  return typeof body === "object" && body !== null && "challenge_id" in body;
}

function isSessionBody(body: unknown): body is LoginSessionBody {
  return typeof body === "object" && body !== null && "user_id" in body;
}

async function login(request: LoginRequest): Promise<LoginResult> {
  const body = await apiClient.post<LoginSessionBody | LoginMfaChallengeBody>("/api/v1/auth/login", request);

  if (isMfaChallengeBody(body)) {
    return { kind: "mfaChallenge", data: body };
  }
  if (isSessionBody(body)) {
    return { kind: "session", data: body };
  }
  throw new Error("useLogin: unrecognized login response shape");
}

export function useLogin() {
  return useMutation({
    mutationFn: login,
    retry: false,
  });
}
