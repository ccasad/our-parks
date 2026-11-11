// The Parks tab's map view: MapLibre GL with OpenFreeMap tiles (FR-9 to FR-11).
// The library is vendored and loaded only when a map is on the page.
(function () {
  var map = null;
  var markers = [];
  var libPromise = null;
  var CONTIGUOUS = { west: -125, east: -66, south: 24, north: 50 };

  function loadLibrary() {
    if (window.maplibregl) return Promise.resolve();
    if (!libPromise) {
      libPromise = new Promise(function (resolve, reject) {
        var css = document.createElement("link");
        css.rel = "stylesheet";
        css.href = "/static/vendor/maplibre-gl.css";
        document.head.appendChild(css);
        var script = document.createElement("script");
        script.src = "/static/vendor/maplibre-gl.js";
        script.onload = resolve;
        script.onerror = function () {
          libPromise = null;
          reject(new Error("map library"));
        };
        document.head.appendChild(script);
      });
    }
    return libPromise;
  }

  function readData() {
    var el = document.getElementById("map-data");
    if (!el) return { points: [] };
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return { points: [] };
    }
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // The small card shown when a marker is tapped. Built with textContent, never innerHTML:
  // park names come from outside.
  function card(point) {
    var box = el("div", "park-card");
    if (point.photo) {
      var img = el("img", "park-card-photo");
      img.src = point.photo;
      img.alt = point.alt || "";
      img.loading = "lazy";
      if (point.credit) img.title = "Photo: " + point.credit;
      box.appendChild(img);
    }
    var body = el("div", "park-card-body");
    body.appendChild(el("p", "park-card-name", point.name));
    if (point.states) body.appendChild(el("p", "park-card-states", point.states));
    var meta = el("p", "park-card-meta");
    if (point.visited) meta.appendChild(el("span", "park-card-badge", "Visited"));
    if (point.rating) {
      var stars = el("span", "park-card-stars", "★".repeat(point.rating) + "☆".repeat(5 - point.rating));
      stars.setAttribute("role", "img");
      stars.setAttribute("aria-label", point.rating + " of 5 stars");
      meta.appendChild(stars);
    }
    body.appendChild(meta);
    var link = el("a", "park-card-link", "Open park page");
    link.href = "/parks/" + encodeURIComponent(point.code);
    body.appendChild(link);
    box.appendChild(body);
    return box;
  }

  function marker(point) {
    var button = el("button", "park-marker " + (point.visited ? "is-visited" : "is-unvisited"));
    button.type = "button";
    button.setAttribute("aria-label", point.name + (point.visited ? ", visited" : ""));
    var m = new maplibregl.Marker({ element: button })
      .setLngLat([point.lon, point.lat])
      .setPopup(new maplibregl.Popup({ offset: 16, maxWidth: "260px" }).setDOMContent(card(point)))
      .addTo(map);
    return m;
  }

  function fit(points) {
    if (!points.length) return;
    // Alaska, Hawaii and the territories would zoom the map out to the whole world,
    // so frame the lower 48 when any parks are there.
    var main = points.filter(function (p) {
      return p.lon >= CONTIGUOUS.west && p.lon <= CONTIGUOUS.east &&
        p.lat >= CONTIGUOUS.south && p.lat <= CONTIGUOUS.north;
    });
    var use = main.length ? main : points;
    var bounds = new maplibregl.LngLatBounds();
    use.forEach(function (p) { bounds.extend([p.lon, p.lat]); });
    map.fitBounds(bounds, { padding: 40, maxZoom: 7, duration: 0 });
  }

  function draw(framed) {
    if (!map) return;
    markers.forEach(function (m) { m.remove(); });
    var points = readData().points || [];
    markers = points.map(marker);
    if (framed) fit(points);
  }

  function failed() {
    var message = document.getElementById("map-error");
    if (message) message.hidden = false;
  }

  function start() {
    var container = document.getElementById("map");
    if (map && map.getContainer() !== container) {
      // hx-boost replaced the page, so the old map's element is gone.
      map.remove();
      map = null;
      markers = [];
    }
    if (!container || map) return;
    loadLibrary().then(function () {
      if (!document.body.contains(container) || map) return;
      map = new maplibregl.Map({
        container: container,
        style: container.dataset.style,
        center: [-98.5, 39.5],
        zoom: 3,
        attributionControl: { compact: true },
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      map.on("error", function (event) {
        // A missing tile isn't fatal; a style that never loads is.
        if (!map.isStyleLoaded()) failed();
        void event;
      });
      draw(true);
    }, failed);
  }

  document.addEventListener("DOMContentLoaded", start);
  document.addEventListener("htmx:afterSettle", function (event) {
    var target = event.detail && event.detail.target;
    if (target && target.id === "results") {
      draw(true); // filters changed: new markers, framed to fit
    } else {
      start();
    }
  });
})();
