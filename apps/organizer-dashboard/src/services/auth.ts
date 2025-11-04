"use client";

const AUTH_BASE_URL =
  process.env.NEXT_PUBLIC_AUTH_API ?? "http://localhost:8001";

export type OrganiserProfile = {
  id: string;
  name: string;
  nric: string;
  role: "organiser" | "admin";
  org_ids: string[];
};

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
};

type OrganiserLoginResponse = {
  user: OrganiserProfile;
  tokens: TokenPair;
};

async function handleResponse<T>(response: Response): Promise<T> {
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const message =
      (payload as any)?.detail ||
      (payload as any)?.message ||
      "Unable to complete request.";
    throw new Error(message);
  }

  return payload as T;
}

export async function organiserLogin({
  username,
  password,
}: {
  username: string;
  password: string;
}): Promise<OrganiserLoginResponse> {
  const response = await fetch(`${AUTH_BASE_URL}/auth/organisers/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ username, password }),
    credentials: "include",
  });

  return handleResponse<OrganiserLoginResponse>(response);
}

export async function organiserRefresh({
  accessToken,
  refreshToken,
}: {
  accessToken: string;
  refreshToken: string;
}): Promise<TokenPair> {
  const response = await fetch(`${AUTH_BASE_URL}/auth/refresh`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ refresh_token: refreshToken }),
    credentials: "include",
  });

  return handleResponse<TokenPair>(response);
}

export async function organiserLogout({
  accessToken,
  refreshToken,
}: {
  accessToken: string;
  refreshToken: string;
}): Promise<void> {
  const response = await fetch(`${AUTH_BASE_URL}/auth/logout`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ refresh_token: refreshToken }),
    credentials: "include",
  });

  if (!response.ok) {
    await handleResponse<unknown>(response);
  }
}

export async function fetchOrganiserProfile({
  accessToken,
}: {
  accessToken: string;
}): Promise<OrganiserProfile> {
  const response = await fetch(`${AUTH_BASE_URL}/users/me`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
    credentials: "include",
  });

  return handleResponse<OrganiserProfile>(response);
}
