import { describe, it, expect, vi, afterEach } from "vitest";
import { apiClient } from "@/lib/api/apiClient";
import type { ApiError } from "@/lib/api/ApiError";
import { submitCustomRequest, toCustomRequestFormData, type CustomRequestFormValues } from "./customRequestApi";
import { BYI_ERROR_COPY, describeCustomRequestFailure } from "./customRequestErrors";
import { CAPTCHA_FAILURE_COPY } from "@/lib/captcha/captchaErrors";

const VALUES: CustomRequestFormValues = {
  name: " Rana ",
  email: " rana@example.com ",
  phone: " +961 70 123 456 ",
  project_title: " Lamp ",
  description: " A lamp\nshaped like a cedar ",
  preferred_material: "",
  preferred_colour: " green ",
  dimensions: "  ",
};

const png = (name: string) => new File([new Uint8Array([137, 80, 78, 71])], name, { type: "image/png" });

afterEach(() => vi.restoreAllMocks());

describe("toCustomRequestFormData", () => {
  it("sends the exact backend parts: trimmed text, blank optionals omitted, one attachments part per file", () => {
    const form = toCustomRequestFormData(VALUES, [png("a.png"), png("b.png")], "tok");
    const text = [...form.entries()].filter(([, v]) => typeof v === "string");
    expect(text).toEqual([
      ["name", "Rana"],
      ["email", "rana@example.com"],
      ["phone", "+961 70 123 456"],
      ["project_title", "Lamp"],
      ["description", "A lamp\nshaped like a cedar"],
      ["preferred_colour", "green"],
      ["captcha_token", "tok"],
    ]);
    expect(form.getAll("attachments").map((f) => (f as File).name)).toEqual(["a.png", "b.png"]);
  });

  it("sends no attachments part when none are selected", () => {
    expect(toCustomRequestFormData(VALUES, [], "tok").has("attachments")).toBe(false);
  });
});

describe("submitCustomRequest", () => {
  it("POSTs multipart to /api/v1/custom-requests without CSRF and with a long timeout", async () => {
    const postForm = vi.spyOn(apiClient, "postForm").mockResolvedValue({ id: "x", created_at: "y" });
    await submitCustomRequest({ values: VALUES, attachments: [], captchaToken: "tok" });
    const [path, body, options] = postForm.mock.calls[0]!;
    expect(path).toBe("/api/v1/custom-requests");
    expect(body).toBeInstanceOf(FormData);
    expect(options).toEqual({ timeoutMs: 180_000 });
  });
});

describe("describeCustomRequestFailure", () => {
  const http = (status: number, extra: Partial<ApiError> = {}): ApiError => ({ kind: "http", status, message: "x", detail: "RAW", raw: {}, ...extra });
  const files = [png("first.png"), png("sketch <b>.png")];

  it("names the rejected file from the visitor's own selection by index", () => {
    const e = http(422, { code: "UPLOAD_REJECTED", errors: [{ loc: ["body", "attachments", 1], msg: "RAW", type: "value_error" }] });
    expect(describeCustomRequestFailure(e, files)).toBe(BYI_ERROR_COPY.uploadRejectedFile("sketch <b>.png"));
  });

  it("falls back to general upload copy without an index (count / body size)", () => {
    const e = http(422, { code: "UPLOAD_REJECTED", errors: [{ loc: ["body", "attachments"], msg: "RAW", type: "value_error" }] });
    expect(describeCustomRequestFailure(e, files)).toBe(BYI_ERROR_COPY.uploadRejected);
  });

  it("maps malware detection, with or without an index", () => {
    expect(describeCustomRequestFailure(http(422, { code: "MALWARE_DETECTED" }), files)).toBe(BYI_ERROR_COPY.malware);
    expect(
      describeCustomRequestFailure(http(422, { code: "MALWARE_DETECTED", errors: [{ loc: ["body", "attachments", 0], msg: "m", type: "value_error" }] }), files)
    ).toBe(BYI_ERROR_COPY.malwareFile("first.png"));
  });

  it("uses one neutral message for any 503 (captcha or scanner)", () => {
    expect(describeCustomRequestFailure(http(503, { code: "SERVICE_UNAVAILABLE" }), files)).toBe(BYI_ERROR_COPY.unavailable);
  });

  it("delegates captcha, field validation and rate limits to the shared mapper", () => {
    expect(describeCustomRequestFailure(http(400, { code: "CAPTCHA_INVALID" }), files)).toBe(CAPTCHA_FAILURE_COPY.invalid);
    expect(
      describeCustomRequestFailure(http(422, { code: "VALIDATION_ERROR", errors: [{ loc: ["body", "project_title"], msg: "RAW", type: "missing" }] }), files)
    ).toBe("Please check: Project title.");
    expect(describeCustomRequestFailure(http(429), files)).toMatch(/Too many submissions/);
  });
});
