// あいミス官网 RSS 反代 —— 跑在日本区（Koyeb TYO）
// 作用：给 GitHub Actions 一个「日本 IP」的入口，绕过 CloudFront 的海外机房封锁。
// 只放行 /news/feed 这一个路径，别的全 404，免得被人当开放代理用。

const ORIGIN = "https://dmm-imys.com";
const ALLOW = [/^\/news\/feed\/?$/, /^\/news\/feed\/\?paged=\d+$/, /^\/feed\/?$/];
const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36";

async function handle(req: Request): Promise<Response> {
  const url = new URL(req.url);
  const path = url.pathname + (url.search || "");

  if (url.pathname === "/" || url.pathname === "/healthz") {
    return new Response("ok\n", { headers: { "content-type": "text/plain" } });
  }

  if (!ALLOW.some((re) => re.test(path))) {
    return new Response("not found\n", { status: 404 });
  }

  const target = ORIGIN + path;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 20000);

  try {
    const r = await fetch(target, {
      signal: ctrl.signal,
      headers: {
        "User-Agent": UA,
        "Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Referer": ORIGIN + "/news/",
      },
      redirect: "follow",
    });
    const body = await r.text();
    return new Response(body, {
      status: r.status,
      headers: {
        "content-type": "application/rss+xml; charset=utf-8",
        "cache-control": "public, max-age=900",
        "x-upstream-status": String(r.status),
        "x-proxy-region": Deno.env.get("KOYEB_REGION") ?? "unknown",
      },
    });
  } catch (e) {
    return new Response("upstream error: " + String(e) + "\n", {
      status: 502,
      headers: { "content-type": "text/plain; charset=utf-8" },
    });
  } finally {
    clearTimeout(timer);
  }
}

Deno.serve({ port: Number(Deno.env.get("PORT") ?? 8000) }, handle);
