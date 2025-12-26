export type HttpError = {
  name: "HttpError";
  status: number;
  url: string;
  bodyText?: string;
};

export async function http<T>(input: RequestInfo | URL, init?: RequestInit) {
  const res = await fetch(input, init);
  if (!res.ok) {
    const bodyText = await safeText(res);
    const err: HttpError = {
      name: "HttpError",
      status: res.status,
      url: typeof input === "string" ? input : String(input),
      bodyText,
    };
    throw err;
  }
  return (await res.json()) as T;
}

async function safeText(res: Response) {
  try {
    return await res.text();
  } catch {
    return undefined;
  }
}

