// imys reverse proxy - deployed on Vercel, function pinned to Tokyo (hnd1).
// GitHub Actions fetches this URL, borrowing a Japanese host to reach dmm-imys.com.
// Allowed: /api/feed (RSS list, optional ?paged=N) and /api/feed?path=/news/<slug>/
// (single news page, used to read exact event periods). Anything else 404.

const ORIGIN = "https://dmm-imys.com";
const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36";

const PAGE_PATH = /^\/news\/[a-z0-9][a-z0-9-]{0,80}\/$/i;

function commonHeaders() {
  return {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
  };
}

async function grab(url, accept) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 20000);
  try {
    return await fetch(url, {
      signal: ctrl.signal,
      redirect: "follow",
      headers: Object.assign(commonHeaders(), { Accept: accept }),
    });
  } finally {
    clearTimeout(timer);
  }
}

export default async function handler(req, res) {
  const { paged, path, probe } = req.query;

  if (probe === "1") {
    const r = await grab(ORIGIN + "/news/feed/", "application/rss+xml");
    res.setHeader("content-type", "application/json; charset=utf-8");
    return res.status(200).json({
      upstream: r.status,
      region: process.env.VERCEL_REGION || "?",
    });
  }

  // single news page
  if (path) {
    if (!PAGE_PATH.test(path)) {
      return res.status(400).send("path not allowed");
    }
    try {
      const r = await grab(ORIGIN + path, "text/html");
      const body = await r.text();
      res.setHeader("content-type", "text/html; charset=utf-8");
      res.setHeader("cache-control", "public, max-age=3600");
      res.setHeader("x-upstream-status", String(r.status));
      return res.status(r.status).send(body);
    } catch (e) {
      res.setHeader("content-type", "text/plain; charset=utf-8");
      return res.status(502).send("upstream error: " + String(e));
    }
  }

  // rss list
  const suffix = paged ? `?paged=${encodeURIComponent(String(paged))}` : "";
  try {
    const r = await grab(
      `${ORIGIN}/news/feed/${suffix}`,
      "application/rss+xml,application/xml;q=0.9,*/*;q=0.8"
    );
    const body = await r.text();
    res.setHeader("content-type", "application/rss+xml; charset=utf-8");
    res.setHeader("cache-control", "public, max-age=900");
    res.setHeader("x-upstream-status", String(r.status));
    res.setHeader("x-proxy-region", process.env.VERCEL_REGION || "?");
    return res.status(r.status).send(body);
  } catch (e) {
    res.setHeader("content-type", "text/plain; charset=utf-8");
    return res.status(502).send("upstream error: " + String(e));
  }
}
