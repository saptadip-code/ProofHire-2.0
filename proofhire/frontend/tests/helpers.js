// Test helpers: a tiny window/localStorage stub and a scripted fetch.
export function installBrowserStubs() {
  const store = new Map();
  const events = [];
  globalThis.window = {
    localStorage: {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => void store.set(k, String(v)),
      removeItem: (k) => void store.delete(k),
    },
    dispatchEvent: (e) => void events.push(e.type),
    addEventListener() {},
    removeEventListener() {},
  };
  return { store, events };
}

export function mockFetch(handler) {
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    const r = await handler(String(url), init, calls.length);
    return {
      status: r.status ?? 200,
      ok: (r.status ?? 200) >= 200 && (r.status ?? 200) < 300,
      text: async () => (r.body === undefined ? '' : typeof r.body === 'string' ? r.body : JSON.stringify(r.body)),
    };
  };
  return calls;
}
