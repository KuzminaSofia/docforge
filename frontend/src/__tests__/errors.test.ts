import {
  ApiError,
  UnauthorizedError,
  ForbiddenError,
  NotFoundError,
  ServerError,
  throwForStatus,
  extractErrorDetail,
} from "@/lib/api/errors";

describe("ApiError", () => {
  it("stores status and detail", () => {
    const err = new ApiError(422, "Validation error");
    expect(err.status).toBe(422);
    expect(err.detail).toBe("Validation error");
    expect(err.message).toBe("Validation error");
    expect(err).toBeInstanceOf(Error);
  });
});

describe("throwForStatus", () => {
  it("throws UnauthorizedError for 401", () => {
    expect(() => throwForStatus(401, "Unauthorized")).toThrow(UnauthorizedError);
  });

  it("throws ForbiddenError for 403", () => {
    expect(() => throwForStatus(403, "Forbidden")).toThrow(ForbiddenError);
  });

  it("throws NotFoundError for 404", () => {
    expect(() => throwForStatus(404, "Not found")).toThrow(NotFoundError);
  });

  it("throws ServerError for 500", () => {
    expect(() => throwForStatus(500, "Internal error")).toThrow(ServerError);
  });

  it("throws ServerError for 503", () => {
    expect(() => throwForStatus(503, "Service unavailable")).toThrow(ServerError);
  });

  it("throws generic ApiError for other statuses", () => {
    expect(() => throwForStatus(409, "Conflict")).toThrow(ApiError);
    try {
      throwForStatus(409, "Conflict");
    } catch (e) {
      expect((e as ApiError).status).toBe(409);
    }
  });
});

function mockResponse(body: unknown, statusText = ""): Response {
  const isString = typeof body === "string";
  return {
    statusText,
    json: () => (isString ? Promise.reject(new SyntaxError()) : Promise.resolve(body)),
    text: () => Promise.resolve(isString ? body : JSON.stringify(body)),
  } as unknown as Response;
}

describe("extractErrorDetail", () => {
  it("extracts string detail from JSON body", async () => {
    const detail = await extractErrorDetail(mockResponse({ detail: "Something went wrong" }));
    expect(detail).toBe("Something went wrong");
  });

  it("joins array detail messages", async () => {
    const body = { detail: [{ msg: "field required" }, { msg: "invalid value" }] };
    const detail = await extractErrorDetail(mockResponse(body));
    expect(detail).toBe("field required; invalid value");
  });

  it("falls back to statusText when body is not JSON", async () => {
    const detail = await extractErrorDetail(mockResponse("plain text", "Internal Server Error"));
    expect(detail).toBe("Internal Server Error");
  });
});
