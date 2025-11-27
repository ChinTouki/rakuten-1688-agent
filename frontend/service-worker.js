const CACHE_NAME = "rakuten-agent-v1";
const URLS_TO_CACHE = [
  "/ui/",
  "/ui/index.html",
  "/ui/manifest.webmanifest",
  "/ui/icon-192.png",
  "/ui/icon-512.png"
];

// 安装：预缓存基本静态资源
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(URLS_TO_CACHE);
    })
  );
  self.skipWaiting();
});

// 激活：清理旧缓存
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      )
    )
  );
  self.clients.claim();
});

// 请求拦截：简单的「キャッシュ優先＋ネットフォールバック」
self.addEventListener("fetch", (event) => {
  const req = event.request;

  // 只处理 GET
  if (req.method !== "GET") {
    return;
  }

  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) {
        // 有缓存就先给缓存，同时后台更新
        fetch(req)
          .then((resp) => {
            const respClone = resp.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(req, respClone);
            });
          })
          .catch(() => {});
        return cached;
      }

      // 没缓存就正常走网络，并写入缓存
      return fetch(req)
        .then((resp) => {
          const respClone = resp.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(req, respClone);
          });
          return resp;
        })
        .catch(() => {
          // 网络失败且无缓存的情况，这里可以返回一个简单的 fallback
          return new Response("オフラインです。ネットワーク接続を確認してください。", {
            status: 503,
            headers: { "Content-Type": "text/plain; charset=utf-8" }
          });
        });
    })
  );
});
