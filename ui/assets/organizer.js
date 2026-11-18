// The organizer view: the whole cohort from GET /organizer on the ideas service, which asks review
// for every idea's labels and gates. The key travels in a header and is kept only for this tab.

var main = document.getElementById("main");
var KEY = "pk-organizer-key";

var RANK = { UNPROVEN: 0, PENDING: 1, PARTIAL: 2, PROVEN: 3 };
var TREND_RANK = { down: 0, none: 1, flat: 2, up: 3 };
var TREND_NAMES = { up: "Improving", down: "Slipping", flat: "Flat", none: "–" };
var STATION_RANK = { prep: 0, grill: 1, tasting: 2, takeaway: 3 };

function savedKey() {
  try {
    return sessionStorage.getItem(KEY) || "";
  } catch (error) {
    return "";
  }
}

function saveKey(key) {
  try {
    if (key) {
      sessionStorage.setItem(KEY, key);
    } else {
      sessionStorage.removeItem(KEY);
    }
  } catch (error) {
    return;
  }
}

function lock(message) {
  main.innerHTML =
    '<section class="panel lock' + (message ? " is-wrong" : "") + '"><span class="lock-icon">' + icon("lock") + "</span>" +
    '<h1>Organizer view</h1><p class="muted">Enter the organizer key to see the whole cohort.</p>' +
    (message ? '<p class="error" role="alert">' + esc(message) + "</p>" : "") +
    '<form class="key-form" data-key-form><span class="key-input">' +
    '<input id="organizer-key" name="key" type="password" autocomplete="current-password" aria-label="Organizer key" required data-main-input />' +
    '<button class="key-show" type="button" data-show-password="organizer-key" aria-label="Show the key" aria-pressed="false">' + icon("eye") + "</button></span>" +
    '<button class="primary" type="submit"><span>Open</span>' + icon("arrow-right") + "</button></form></section>";
  setUp(main);
  main.querySelector("#organizer-key").focus();
}

function metric(index, value, name, alert) {
  return (
    '<div class="ticket metric' + (alert ? " metric-alert" : "") + '" style="--i: ' + index + '">' +
    '<span class="metric-value" data-count>' + esc(value) + '</span><span class="metric-name">' + esc(name) + "</span></div>"
  );
}

function percent(share) {
  return Math.round(share * 100) + "%";
}

function row(item) {
  var status = ["parked", "served", "binned"].indexOf(item.status) !== -1 ? " · " + esc(item.status) : "";
  return (
    "<tr" + (item.stuck ? ' class="row-stuck"' : "") + ">" +
    "<td>" + (item.stuck ? '<span class="stuck-dot" aria-hidden="true"></span>' : "") + esc(item.display_name) + "</td>" +
    '<td><a href="idea.html?t=' + encodeURIComponent(item.token) + '">' + esc(item.one_liner) + "</a></td>" +
    '<td data-value="' + STATION_RANK[item.station] + '">' + esc(item.station_name) + status + "</td>" +
    '<td data-value="' + RANK[item.label] + '">' + stamp({ label: item.label }) + "</td>" +
    '<td class="trend trend-' + item.trend + '" data-value="' + TREND_RANK[item.trend] + '">' + TREND_NAMES[item.trend] + "</td>" +
    "<td>" + item.answers + "</td><td>" + item.logs + "</td><td>" + item.gates_passed + "</td>" +
    '<td data-value="' + esc(item.last_activity) + '">' + esc(item.last_activity) + (item.stuck ? " · " + item.days_idle + "d idle" : "") + "</td></tr>"
  );
}

function render(found) {
  var m = found.metrics;
  var top = m.funnel[0][1] || 1;
  var funnel = m.funnel
    .map(function (step, index) {
      var share = (step[1] / top) * 100;
      return (
        '<div class="funnel-row" style="--i: ' + index + '"><span>' + esc(step[0]) + "</span>" +
        '<div class="bar-track" data-tip="' + Math.round(share) + '% of everyone who pitched"><div class="bar-fill funnel-fill" style="--w: ' + share + '%"></div></div>' +
        '<span class="bar-value">' + step[1] + "</span></div>"
      );
    })
    .join("");
  var table = found.rows.length
    ? '<div class="table-tools"><label class="filter">' + icon("search") +
      '<input type="search" placeholder="Filter by founder, idea, or station" aria-label="Filter the table" data-filter="#cohort-table" /></label>' +
      '<span class="muted" data-filter-count>' + plural(found.rows.length, "idea") + "</span></div>" +
      '<div class="table-wrap"><table class="cohort-table" id="cohort-table"><thead><tr>' +
      ["Founder", "Idea", "Station", "Verdict", "Trend", "Answers", "Talks", "Gates", "Last active"]
        .map(function (name) { return '<th><button type="button" data-sort>' + name + "</button></th>"; })
        .join("") +
      "</tr></thead><tbody>" + found.rows.map(row).join("") + "</tbody></table></div>"
    : '<div class="empty"><span class="empty-icon">' + icon("users") + "</span><p>No ideas yet.</p></div>";
  main.innerHTML =
    '<div class="section-head org-head"><h1>Cohort</h1><p>As of ' + esc(found.today) + "</p>" +
    '<button class="tool" type="button" data-sign-out>' + icon("lock") + "<span>Lock</span></button></div>" +
    '<section class="metrics">' +
    metric(0, m.ideas, "Ideas from " + plural(m.founders, "founder")) +
    metric(1, m.active_this_week, "Active in the last 7 days") +
    metric(2, m.answers_per_idea, "Answers per idea") +
    metric(3, percent(m.reached_tasting), "Talked to real people") +
    metric(4, percent(m.returning_founders), "Founders who came back another day") +
    metric(5, m.stuck, "Stuck 7+ days", m.stuck > 0) +
    "</section>" +
    '<section class="panel"><h2>Funnel</h2><div class="funnel">' + funnel + "</div></section>" +
    '<section><div class="section-head"><h2>Who needs a nudge</h2><p>Stuck first, then longest idle</p></div>' + table + "</section>";
  setUp(main);
}

function openCohort(key) {
  loading(main, "Counting the cohort…");
  api
    .ideas("/organizer", { headers: { "X-Organizer-Key": key } })
    .then(function (found) {
      saveKey(key);
      render(found);
    })
    .catch(function (error) {
      if (error.status === 403) {
        saveKey("");
        lock(error.message);
      } else if (error.status === 404) {
        main.innerHTML = '<section class="page-state"><p>The organizer view is turned off on this kitchen.</p></section>';
      } else {
        failed(main, error, function () {
          openCohort(key);
        });
      }
    });
}

main.addEventListener("submit", function (event) {
  if (event.target.matches("[data-key-form]")) {
    event.preventDefault();
    openCohort(event.target.elements.key.value);
  }
});

main.addEventListener("click", function (event) {
  if (event.target.closest("[data-sign-out]")) {
    saveKey("");
    lock();
  }
});

if (savedKey()) {
  openCohort(savedKey());
} else {
  lock();
}
