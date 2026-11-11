// "Near me" on the Parks tab (FR-7). The browser's location goes to the server in a POST
// body only: never in the URL, and the page keeps it in form fields, not in storage.
(function () {
  function form() {
    return document.getElementById("filters");
  }

  function field(name) {
    var f = form();
    return f ? f.elements[name] : null;
  }

  function isOn() {
    var lat = field("lat");
    return !!(lat && !lat.disabled && lat.value !== "");
  }

  function message(text) {
    var box = document.getElementById("near-message");
    if (!box) return;
    box.textContent = text || "";
    box.hidden = !text;
  }

  function setOn(on, lat, lon) {
    var f = form();
    var options = f.querySelector("[data-near-options]");
    var button = f.querySelector("[data-near-toggle]");
    ["lat", "lon", "radius"].forEach(function (name) {
      field(name).disabled = !on;
    });
    field("lat").value = on ? lat : "";
    field("lon").value = on ? lon : "";
    options.hidden = !on;
    // Near me selects Distance; turning it off returns from Distance to Name A–Z (FR-21).
    var sort = field("sort");
    if (sort) {
      var option = sort.tagName === "SELECT" ? sort.querySelector('option[value="distance"]') : null;
      if (option) {
        option.disabled = !on;
        option.hidden = !on;
      }
      if (on) sort.value = "distance";
      else if (sort.value === "distance") sort.value = "name";
    }
    button.setAttribute("aria-pressed", on ? "true" : "false");
    var classes = {
      on: ["border-sky-600", "bg-sky-50", "text-sky-800"],
      off: ["border-slate-300", "bg-white"],
    };
    classes.on.forEach(function (c) { button.classList.toggle(c, on); });
    classes.off.forEach(function (c) { button.classList.toggle(c, !on); });
  }

  function refresh() {
    form().dispatchEvent(new Event("change", { bubbles: true }));
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-near-toggle]");
    if (!button) return;
    message("");
    if (isOn()) {
      setOn(false);
      refresh();
      return;
    }
    if (!navigator.geolocation) {
      message("This browser can't share your location, so the list is unchanged.");
      return;
    }
    var label = button.querySelector("span");
    var original = label.textContent;
    button.disabled = true;
    label.textContent = "Locating…";
    navigator.geolocation.getCurrentPosition(
      function (position) {
        button.disabled = false;
        label.textContent = original;
        // About 100 m is plenty for "how far is it".
        setOn(true, position.coords.latitude.toFixed(3), position.coords.longitude.toFixed(3));
        refresh();
      },
      function (error) {
        button.disabled = false;
        label.textContent = original;
        message(
          error && error.code === 1
            ? "Location access was denied, so the list is unchanged. You can allow it in your browser's settings."
            : "Your location couldn't be found, so the list is unchanged. Try again."
        );
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
    );
  });

  // While Near me is on, filter requests go as a POST with the location in the body.
  document.addEventListener("htmx:configRequest", function (event) {
    var elt = event.detail.elt;
    if ((elt !== form() && !(elt.hasAttribute && elt.hasAttribute("data-sort"))) || !isOn()) return;
    event.detail.verb = "post";
    event.detail.path = "/parks/near";
    event.detail.useUrlParams = false;
  });

  // The List / Map toggle is a link, which would put the location in the URL or lose it,
  // so with Near me on it posts the form instead.
  document.addEventListener("click", function (event) {
    var toggle = event.target.closest("[data-view-toggle]");
    if (!toggle || !form() || !isOn()) return;
    event.preventDefault();
    var post = document.createElement("form");
    post.method = "post";
    post.action = "/parks/near";
    var data = new FormData(form());
    data.set("view", toggle.dataset.viewToggle);
    data.forEach(function (value, key) {
      var input = document.createElement("input");
      input.type = "hidden";
      input.name = key;
      input.value = value;
      post.appendChild(input);
    });
    document.body.appendChild(post);
    post.submit();
  });
})();
