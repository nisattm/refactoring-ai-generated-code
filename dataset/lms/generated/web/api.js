// REST client: the only way the interface talks to the server (LIB-UI-GEN-01).

const API = "/api/v1";
const TOKEN_KEY = "lms.token";
const USER_KEY = "lms.user";
const RETURN_KEY = "lms.return";

export const session = {
  token: () => sessionStorage.getItem(TOKEN_KEY),
  user() {
    try {
      return JSON.parse(sessionStorage.getItem(USER_KEY) || "null");
    } catch {
      return null;
    }
  },
  set(token, user) {
    sessionStorage.setItem(TOKEN_KEY, token);
    sessionStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  setUser: (user) => sessionStorage.setItem(USER_KEY, JSON.stringify(user)),
  clear() {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
  },
  returnTo: () => sessionStorage.getItem(RETURN_KEY),
  setReturnTo: (hash) => sessionStorage.setItem(RETURN_KEY, hash),
  clearReturnTo: () => sessionStorage.removeItem(RETURN_KEY),
};

export class ApiError extends Error {
  constructor(status, code, message, details = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details || {};
  }
}

export const NETWORK_MESSAGE = "The server cannot be reached.";

// Raised by the interface itself (for example when a member number matches nobody).
export function clientError(code, message, details = {}) {
  return new ApiError(0, code, message, details);
}

export function queryString(query) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query || {})) {
    if (value === undefined || value === null || value === "") continue;
    params.append(key, String(value));
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

function unauthorized() {
  document.dispatchEvent(new CustomEvent("lms:unauthorized"));
}

async function send(method, path, { query, body, rawBody, auth = true } = {}) {
  const headers = {};
  const token = session.token();
  if (auth && token) headers.Authorization = `Bearer ${token}`;
  const init = { method, headers };
  if (rawBody !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = rawBody;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(`${path}${queryString(query)}`, init);
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", NETWORK_MESSAGE);
  }
  return response;
}

async function toError(response, auth) {
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  const error = payload && payload.error ? payload.error : {};
  // A wrong current password (INVALID_CREDENTIALS, LIB-AUTH-16) is an ordinary error; the session is still valid.
  if (response.status === 401 && auth && error.code !== "INVALID_CREDENTIALS") unauthorized();
  return new ApiError(
    response.status,
    error.code || `HTTP_${response.status}`,
    error.message || response.statusText || "Request failed",
    error.details || {},
  );
}

export async function api(method, path, options = {}) {
  const auth = options.auth !== false;
  const response = await send(method, `${API}${path}`, options);
  if (!response.ok) throw await toError(response, auth);
  if (response.status === 204) return null;
  try {
    return await response.json();
  } catch {
    throw new ApiError(response.status, "INVALID_RESPONSE", "The server sent an unreadable answer.");
  }
}

export const get = (path, query) => api("GET", path, { query });
export const post = (path, body) => api("POST", path, body === undefined ? {} : { body });
export const patch = (path, body) => api("PATCH", path, { body });
export const del = (path) => api("DELETE", path);

// Downloads a file that needs the session token and hands it to the browser.
export async function download(path, filename) {
  const response = await send("GET", `${API}${path}`, {});
  if (!response.ok) throw await toError(response, true);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function health() {
  const response = await send("GET", "/health", { auth: false });
  if (!response.ok) throw await toError(response, false);
  return response.json();
}

// Reads every page of a list endpoint (short lists such as branches or publishers).
export async function fetchAll(path, query = {}, maxPages = 20) {
  const items = [];
  for (let page = 1; page <= maxPages; page += 1) {
    const data = await get(path, { ...query, page, page_size: 100 });
    items.push(...data.items);
    if (items.length >= data.total || data.items.length === 0) break;
  }
  return items;
}
