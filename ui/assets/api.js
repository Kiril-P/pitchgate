// Every call to the two services goes through here: JSON in and out, a timeout on each call,
// and one designed message for a service that is asleep, waking up, or unreachable.

var CONFIG = window.PK_CONFIG || {};

// Calls that wait for Jev or Chef take longer: the ideas service gives review 90 seconds.
var TIMEOUT_MS = 45000;
var SLOW_TIMEOUT_MS = 120000;

var WAKING =
  "The kitchen is waking up. Both services sleep when nobody is using them, and starting them " +
  "and their databases can take up to a minute. Nothing was lost; try again in a moment.";

function ApiError(message, status, field, waking) {
  this.message = message;
  this.status = status;
  this.field = field || null;
  this.waking = Boolean(waking);
}

// A service always answers with {"error": "..."}. A reply without one came from the platform in
// front of a container that isn't ready, so it gets the waking-up message. A cold start's 503 has
// no CORS headers either, which the browser reports as a network error: same message.
function call(base, path, options) {
  options = options || {};
  var controller = new AbortController();
  var timer = setTimeout(function () {
    controller.abort();
  }, options.slow ? SLOW_TIMEOUT_MS : TIMEOUT_MS);
  var init = { method: options.method || "GET", headers: {}, signal: controller.signal };
  if (options.body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }
  Object.keys(options.headers || {}).forEach(function (name) {
    init.headers[name] = options.headers[name];
  });
  startLoading();
  return fetch(base + path, init)
    .then(
      function (response) {
        if (response.status === 204) {
          return null;
        }
        return response
          .json()
          .catch(function () {
            return null;
          })
          .then(function (data) {
            if (response.ok && data) {
              return data;
            }
            if (data && data.error) {
              throw new ApiError(data.error, response.status, data.field);
            }
            throw new ApiError(WAKING, response.status, null, true);
          });
      },
      function () {
        throw new ApiError(WAKING, 0, null, true);
      }
    )
    .finally(function () {
      clearTimeout(timer);
      finishLoading();
    });
}

var api = {
  ideas: function (path, options) {
    return call(CONFIG.ideasUrl, path, options);
  },
  review: function (path, options) {
    return call(CONFIG.reviewUrl, path, options);
  },
  ideasUrl: function (path) {
    return CONFIG.ideasUrl + path;
  },
};

// The ideas this browser created. Their tokens are the only key to them, so they stay on this device.
var MINE = "pk-ideas";

function myTokens() {
  return (store.get(MINE) || "").split(",").filter(Boolean);
}

function remember(token) {
  store.set(MINE, myTokens().filter(function (t) { return t !== token; }).concat([token]).join(","));
}

function forgetToken(token) {
  store.set(MINE, myTokens().filter(function (t) { return t !== token; }).join(","));
}
