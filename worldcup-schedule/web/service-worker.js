const CACHE_NAME = "worldcup-schedule-v12";
const ASSETS = [
  "./",
  "./index.html",
  "./style.css?v=12",
  "./app.js?v=12",
  "./manifest.json",
  "../data/app_data.json",
  "../data/static_schedule.csv",
  "../data/live_results.json",
  "../data/standings.json",
  "../data/top_scorers.json",
  "../data/knockout_bracket.json",
  "../data/last_updated.json",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      })
      .catch(() => caches.match(event.request).then((cached) => cached || caches.match("./index.html"))),
  );
});
