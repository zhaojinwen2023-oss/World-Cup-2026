const CACHE_NAME = "worldcup-schedule-v16";
const ASSETS = [
  "./",
  "./index.html",
  "./style.css?v=16",
  "./app.js?v=16",
  "./predictions.html",
  "./predictions.html?embedded=1",
  "./predictions.css?v=1",
  "./predictions.js?v=1",
  "./manifest.json",
  "../data/app_data.json",
  "../data/static_schedule.csv",
  "../data/live_results.json",
  "../data/standings.json",
  "../data/top_scorers.json",
  "../data/champion_predictions.json",
  "../data/tournament_predictions.json",
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
      .catch(async () => {
        const cached = await caches.match(event.request);
        if (cached) return cached;
        if (event.request.mode === "navigate") return caches.match("./index.html");
        return Response.error();
      }),
  );
});
