// The small interactions on every page. Like chat.js, listeners sit on the document
// because htmx swaps <body>; setUp runs again on every piece of content htmx loads.

var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
var finePointer = window.matchMedia("(hover: hover) and (pointer: fine)");
var isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);

// localStorage throws in some private windows; every feature that uses it is optional.
var store = {
  get: function (key) {
    try {
      return localStorage.getItem(key);
    } catch (error) {
      return null;
    }
  },
  set: function (key, value) {
    try {
      if (value) {
        localStorage.setItem(key, value);
      } else {
        localStorage.removeItem(key);
      }
    } catch (error) {
      return;
    }
  },
};

function each(root, selector, run) {
  if (root.matches && root.matches(selector)) {
    run(root);
  }
  root.querySelectorAll(selector).forEach(run);
}

function changed(field) {
  field.dispatchEvent(new Event("input", { bubbles: true }));
}

function pad(number) {
  return String(number).padStart(2, "0");
}

function setUp(root) {
  each(root, "time[data-time]", localTime);
  each(root, "[data-mod]", function (key) {
    key.textContent = isMac ? "⌘" : "Ctrl";
  });
  each(root, "[data-draft]", restoreDraft);
  each(root, "textarea[data-autosize]", autosize);
  each(root, "[data-recipe-input]", checkRecipe);
  each(root, "[data-hints]", checkHints);
  each(root, "[data-reply-to]", showReplyTo);
  each(root, "[data-checklist]", restoreChecklist);
  each(root, "[data-date-for]", markDateChip);
  each(root, "[data-count]", countUp);
  each(root, "[data-celebrate]", celebrateOnce);
  tick();
}

htmx.onLoad(setUp);

// Times are stored in UTC; show them in the reader's own time zone.
function localTime(element) {
  var date = new Date(element.getAttribute("datetime"));
  if (isNaN(date)) {
    return;
  }
  var clock = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (element.dataset.time === "clock") {
    element.textContent = clock;
  } else if (element.dataset.time === "ago") {
    element.textContent = ago(date);
  } else {
    element.textContent = dayName(date) + " " + clock;
  }
  element.title = date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function startOfDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function dayName(date) {
  var days = Math.round((startOfDay(new Date()) - startOfDay(date)) / 86400000);
  if (days === 0) {
    return "Today";
  }
  if (days === 1) {
    return "Yesterday";
  }
  return date.toLocaleDateString([], { day: "numeric", month: "short" });
}

function ago(date) {
  var minutes = Math.round((Date.now() - date) / 60000);
  if (minutes < 1) {
    return "just now";
  }
  if (minutes < 60) {
    return minutes + " min ago";
  }
  var hours = Math.round(minutes / 60);
  if (hours < 24) {
    return hours + " h ago";
  }
  var days = Math.round(hours / 24);
  if (days < 7) {
    return days + " d ago";
  }
  return date.toLocaleDateString([], { day: "numeric", month: "short" });
}

// The kitchen clock in the top bar and on the order ticket.
function tick() {
  var now = new Date();
  var shown = pad(now.getHours()) + ":" + pad(now.getMinutes());
  document.querySelectorAll("[data-clock]").forEach(function (clock) {
    if (clock.dataset.shown !== shown) {
      clock.dataset.shown = shown;
      clock.innerHTML = pad(now.getHours()) + '<span class="colon">:</span>' + pad(now.getMinutes());
    }
  });
}

setInterval(tick, 1000);

// Typing: character counters, growing text boxes, saved drafts, and live hints.
function updateCounter(field) {
  var box = field.closest(".field, .composer");
  var counter = box && box.querySelector(".counter");
  var limit = Number(field.getAttribute("maxlength"));
  if (!counter || !limit) {
    return;
  }
  var length = field.value.length;
  counter.textContent = length + " / " + limit;
  counter.classList.toggle("is-near", length >= limit * 0.8 && length < limit);
  counter.classList.toggle("is-full", length >= limit);
}

function autosize(area) {
  if (!area.offsetParent) {
    return;
  }
  area.style.height = "auto";
  area.style.height = area.scrollHeight + area.offsetHeight - area.clientHeight + "px";
  area.style.overflowY = area.scrollHeight > area.clientHeight ? "auto" : "hidden";
}

function draftKey(field) {
  return "pk-draft:" + location.pathname + ":" + field.name;
}

function restoreDraft(field) {
  var saved = store.get(draftKey(field));
  if (saved && !field.value) {
    field.value = saved;
    changed(field);
  }
}

function checkRecipe(input) {
  var text = input.value.toLowerCase();
  input.closest(".field").querySelectorAll("[data-has]").forEach(function (chip) {
    chip.classList.toggle("on", text.indexOf(chip.dataset.has) !== -1);
  });
}

// Rough hints for "who, when, how many". Jev does the real scoring.
var NOT_NAMES = /^(We|The|They|It|My|Our|Their|He|She|His|Her|This|That|These|Those|There|Then|When|What|Who|Why|How|If|So|But|And|Or|Most|Some|Many|All|Every|Everyone|Nobody|No|Yes|People|An|In|On|At|After|Before|Since|For|From|To|Of|With|About|Not|Only|Just|Also|Last|Next|Today|Yesterday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|January|February|March|April|May|June|July|August|September|October|November|December)$/;

var HINTS = {
  who: function (text) {
    var role = /\b(students?|flatmates?|friends?|customers?|users?|sellers?|buyers?|owners?|managers?|staff|parents?|mum|mom|dad|sister|brother|aunt|uncle|colleagues?|classmates?|teachers?|professors?|nurses?|doctors?|clients?)\b/i;
    var names = text.match(/\b[A-Z][a-zà-ÿ]+/g) || [];
    return role.test(text) || names.some(function (word) {
      return !NOT_NAMES.test(word);
    });
  },
  when: function (text) {
    return /\b(yesterday|today|tonight|ago|last|since|monday|tuesday|wednesday|thursday|friday|saturday|sunday|january|february|march|april|june|july|august|september|october|november|december|weeks?|months?|term|semester|morning|evening)\b|\b\d{1,2}[/.]\d{1,2}\b|\b(19|20)\d\d\b/i.test(text);
  },
  number: function (text) {
    return /\d|[€$£%]|\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|hundred|dozen|half)\b/i.test(text);
  },
};

function checkHints(field) {
  field.form.querySelectorAll("[data-hint]").forEach(function (hint) {
    hint.classList.toggle("on", HINTS[hint.dataset.hint](field.value));
  });
}

document.addEventListener("input", function (event) {
  var field = event.target;
  if (field.matches("[maxlength]")) {
    updateCounter(field);
  }
  if (field.matches("textarea[data-autosize]")) {
    autosize(field);
  }
  if (field.matches("[data-draft]")) {
    store.set(draftKey(field), field.value);
  }
  if (field.matches("[data-recipe-input]")) {
    checkRecipe(field);
  }
  if (field.matches("[data-hints]")) {
    checkHints(field);
  }
  if (field.matches("[data-filter]")) {
    filterTable(field);
  }
});

// A closed <details> has no height to measure, so size the edit box when it opens.
document.addEventListener(
  "toggle",
  function (event) {
    var area = event.target.querySelector && event.target.querySelector("textarea[data-autosize]");
    if (area && event.target.open) {
      autosize(area);
      area.focus();
      area.setSelectionRange(area.value.length, area.value.length);
    }
  },
  true
);

// A draft is done once the server took it. Display name is kept for the next pitch.
document.addEventListener("htmx:afterRequest", function (event) {
  var form = event.detail.elt;
  if (form.tagName !== "FORM" || !event.detail.xhr || event.detail.xhr.status >= 400) {
    return;
  }
  form.querySelectorAll("[data-draft]").forEach(function (field) {
    if (field.dataset.draft !== "keep") {
      store.set(draftKey(field), "");
    }
  });
});

// The composer reminds the founder which question they are answering.
function latestQuestion() {
  var turns = document.querySelectorAll(".thread .message.chef:not(.message-paused)");
  var latest = turns[turns.length - 1];
  return latest && latest.querySelector(".bubble-question") ? latest : null;
}

function showReplyTo(button) {
  var turn = latestQuestion();
  button.hidden = !turn;
  if (turn) {
    var question = turn.querySelector(".bubble-question").textContent;
    button.querySelector("[data-reply-text]").textContent = question;
    button.title = question;
  }
}

function flash(message) {
  message.classList.remove("is-flashing");
  void message.offsetWidth;
  message.classList.add("is-flashing");
}

// Checklists for homework and next steps, remembered in this browser.
function checklistKey(list) {
  return "pk-check:" + list.dataset.checklist;
}

function restoreChecklist(list) {
  var done = (store.get(checklistKey(list)) || "").split(",");
  list.querySelectorAll("input[type=checkbox]").forEach(function (box, index) {
    box.checked = done.indexOf(String(index)) !== -1;
  });
}

function saveChecklist(list) {
  var boxes = Array.prototype.slice.call(list.querySelectorAll("input[type=checkbox]"));
  var done = [];
  boxes.forEach(function (box, index) {
    if (box.checked) {
      done.push(index);
    }
  });
  store.set(checklistKey(list), done.join(","));
  return done.length === boxes.length;
}

// Date shortcuts on the conversation log. The server's "today" is the latest allowed day.
function localDay(offset, input) {
  var date = new Date();
  date.setDate(date.getDate() + offset);
  var day = date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate());
  return input.max && day > input.max ? input.max : day;
}

function markDateChip(button) {
  var input = document.getElementById(button.dataset.dateFor);
  if (input) {
    button.classList.toggle("on", input.value === localDay(Number(button.dataset.date), input));
  }
}

document.addEventListener("change", function (event) {
  var list = event.target.closest("[data-checklist]");
  if (list && saveChecklist(list) && event.target.checked) {
    burstFrom(event.target, 60);
    toast("All done. Nice.", "ok");
  }
  if (event.target.type === "date") {
    document.querySelectorAll('[data-date-for="' + event.target.id + '"]').forEach(markDateChip);
  }
});

// Feedback: toasts, copying, the service bell, confetti.
function toast(message, kind) {
  var shelf = document.querySelector("[data-toasts]");
  if (!shelf) {
    return;
  }
  var item = document.createElement("div");
  item.className = "toast" + (kind ? " toast-" + kind : "");
  item.textContent = message;
  shelf.appendChild(item);
  setTimeout(function () {
    item.classList.add("is-leaving");
  }, 2600);
  setTimeout(function () {
    item.remove();
  }, 2950);
}

// navigator.clipboard only exists on https and localhost; the textarea trick covers a LAN address.
function copy(text, message) {
  function done() {
    toast(message, "ok");
  }
  function fallback() {
    var area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    var copied = false;
    try {
      copied = document.execCommand("copy");
    } catch (error) {
      copied = false;
    }
    area.remove();
    if (copied) {
      done();
    } else {
      toast("Couldn't copy. Select the text and copy it by hand.", "error");
    }
  }
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(done, fallback);
  } else {
    fallback();
  }
}

function markDone(button) {
  button.classList.add("is-done");
  setTimeout(function () {
    button.classList.remove("is-done");
  }, 1600);
}

var audio = null;
var rings = [];

// A desk bell: one short tone plus two quieter, faster-fading overtones.
function ding() {
  var Context = window.AudioContext || window.webkitAudioContext;
  if (!Context) {
    return;
  }
  audio = audio || new Context();
  if (audio.state === "suspended") {
    audio.resume();
  }
  var now = audio.currentTime;
  [1, 2.76, 5.4].forEach(function (ratio, index) {
    var tone = audio.createOscillator();
    var gain = audio.createGain();
    tone.frequency.value = 1320 * ratio;
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.16 / (index + 1), now + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 1.6 - index * 0.4);
    tone.connect(gain);
    gain.connect(audio.destination);
    tone.start(now);
    tone.stop(now + 1.7);
  });
}

function ring(bell) {
  ding();
  bell.classList.remove("is-ringing");
  void bell.offsetWidth;
  bell.classList.add("is-ringing");
  var now = Date.now();
  rings = rings.filter(function (time) {
    return now - time < 3000;
  });
  rings.push(now);
  if (rings.length === 5) {
    rings = [];
    toast("WHERE’S THE LAMB SAUCE?!", "hot");
  }
}

document.addEventListener("animationend", function (event) {
  var bell = event.target.closest && event.target.closest(".bell");
  if (bell) {
    bell.classList.remove("is-ringing");
  }
});

var COLORS = ["#ff6a2b", "#ffb648", "#3fa66b", "#f7f1e5", "#d93f3f", "#74d69a"];

function confetti(x, y, count) {
  if (reduceMotion.matches) {
    return;
  }
  var layer = document.createElement("div");
  layer.className = "confetti";
  layer.setAttribute("aria-hidden", "true");
  for (var index = 0; index < count; index++) {
    var bit = document.createElement("i");
    var angle = Math.random() * Math.PI * 2;
    var speed = 90 + Math.random() * 240;
    bit.style.left = x + "px";
    bit.style.top = y + "px";
    bit.style.background = COLORS[index % COLORS.length];
    bit.style.animationDelay = Math.random() * 90 + "ms";
    bit.style.setProperty("--dx", Math.cos(angle) * speed + "px");
    bit.style.setProperty("--dy", Math.sin(angle) * speed - 150 + "px");
    bit.style.setProperty("--spin", Math.random() * 900 - 450 + "deg");
    layer.appendChild(bit);
  }
  document.body.appendChild(layer);
  setTimeout(function () {
    layer.remove();
  }, 1800);
}

function burstFrom(element, count) {
  var box = element.getBoundingClientRect();
  var x = Math.min(Math.max(box.left + box.width / 2, 40), window.innerWidth - 40);
  var y = Math.min(Math.max(box.top + box.height / 2, 80), window.innerHeight - 80);
  confetti(x, y, count);
}

// Served ideas and passed gates get confetti the first time they are seen in this browser.
function celebrateOnce(element) {
  var key = "pk-party:" + element.dataset.celebrate;
  if (store.get(key)) {
    return;
  }
  store.set(key, "yes");
  setTimeout(function () {
    burstFrom(element.querySelector(".ending-icon, .gate-badge") || element, 140);
  }, 700);
}

// Organizer numbers count up from zero, then land on the exact text the server wrote.
function countUp(element) {
  var text = element.textContent.trim();
  var match = text.match(/^(\d+(?:\.\d+)?)(.*)$/);
  if (!match || reduceMotion.matches) {
    return;
  }
  var target = parseFloat(match[1]);
  var decimals = (match[1].split(".")[1] || "").length;
  var start = performance.now();
  function frame(now) {
    var progress = Math.min(1, (now - start) / 900);
    var eased = 1 - Math.pow(1 - progress, 3);
    element.textContent = (target * eased).toFixed(decimals) + match[2];
    if (progress < 1) {
      requestAnimationFrame(frame);
    } else {
      element.textContent = text;
    }
  }
  requestAnimationFrame(frame);
}

// The organizer table: filter by any text in a row, sort by any column.
function filterTable(input) {
  var table = document.querySelector(input.dataset.filter);
  var query = input.value.trim().toLowerCase();
  var rows = table.tBodies[0].querySelectorAll("tr:not(.no-match)");
  var shown = 0;
  rows.forEach(function (row) {
    var hit = row.textContent.toLowerCase().indexOf(query) !== -1;
    row.hidden = !hit;
    shown += hit ? 1 : 0;
  });
  var empty = table.querySelector(".no-match");
  if (!empty) {
    empty = table.tBodies[0].insertRow();
    empty.className = "no-match";
    empty.insertCell().colSpan = table.tHead.rows[0].cells.length;
  }
  empty.hidden = shown > 0;
  empty.cells[0].textContent = "No ideas match “" + input.value.trim() + "”.";
  var count = document.querySelector("[data-filter-count]");
  if (count) {
    count.textContent = query ? shown + " of " + rows.length + " ideas" : rows.length + " idea" + (rows.length === 1 ? "" : "s");
  }
}

function sortKey(cell) {
  var raw = cell.dataset.value !== undefined ? cell.dataset.value : cell.textContent.trim();
  var number = Number(raw);
  return raw !== "" && !isNaN(number) ? number : raw.toLowerCase();
}

function sortTable(header) {
  var table = header.closest("table");
  var column = Array.prototype.indexOf.call(header.parentNode.children, header);
  var ascending = header.getAttribute("aria-sort") !== "ascending";
  table.querySelectorAll("th").forEach(function (cell) {
    cell.removeAttribute("aria-sort");
  });
  header.setAttribute("aria-sort", ascending ? "ascending" : "descending");
  var body = table.tBodies[0];
  var rows = Array.prototype.slice.call(body.querySelectorAll("tr:not(.no-match)"));
  rows.sort(function (first, second) {
    var a = sortKey(first.cells[column]);
    var b = sortKey(second.cells[column]);
    var order = typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b));
    return ascending ? order : -order;
  });
  rows.forEach(function (row) {
    body.appendChild(row);
  });
}

// The Prep suggestions type themselves into the one-liner field.
var typing = null;

function typeInto(input, text) {
  clearInterval(typing);
  input.focus();
  if (reduceMotion.matches) {
    input.value = text;
    changed(input);
    return;
  }
  var shown = 0;
  typing = setInterval(function () {
    shown = Math.min(text.length, shown + 2);
    input.value = text.slice(0, shown);
    changed(input);
    if (shown === text.length) {
      clearInterval(typing);
    }
  }, 14);
}

function restamp(stamp) {
  var ticket = stamp.closest(".ticket");
  stamp.style.animation = "none";
  ticket.style.animation = "none";
  void stamp.offsetWidth;
  stamp.style.animation = "";
  stamp.style.animationDelay = "0s";
  ticket.style.animation = "thud 0.35s ease-out 0.33s";
}

function openDialog(name) {
  var dialog = document.getElementById(name + "-dialog");
  if (dialog && !dialog.open) {
    dialog.showModal();
  }
}

document.addEventListener("click", function (event) {
  var target = event.target.closest ? event.target : null;
  if (!target) {
    return;
  }
  if (target.tagName === "DIALOG") {
    target.close();
    return;
  }
  var found;
  if ((found = target.closest("[data-bell]"))) {
    ring(found);
  } else if ((found = target.closest("[data-open-dialog]"))) {
    openDialog(found.dataset.openDialog);
  } else if ((found = target.closest("[data-copy-link]"))) {
    copy(location.origin + location.pathname, "Link copied. Anyone with it can open this idea.");
    markDone(found);
  } else if ((found = target.closest("[data-copy]"))) {
    copy(document.querySelector(found.dataset.copy).textContent.trim(), found.dataset.copyMessage || "Copied.");
    markDone(found);
  } else if ((found = target.closest("[data-copy-self]"))) {
    copy(found.textContent.trim(), "Question copied. Go ask it.");
    found.classList.add("is-done");
  } else if ((found = target.closest("[data-fill]"))) {
    var story = document.querySelector("textarea[name=story]");
    if (found.dataset.story && story) {
      story.value = found.dataset.story;
      changed(story);
    }
    typeInto(document.getElementById("one-liner"), found.dataset.fill);
    found.parentNode.querySelectorAll(".suggestion").forEach(function (choice) {
      choice.classList.toggle("is-picked", choice === found);
    });
  } else if ((found = target.closest("[data-open-details]"))) {
    var details = document.getElementById(found.dataset.openDetails);
    details.open = true;
    details.scrollIntoView({ behavior: "smooth", block: "center" });
  } else if ((found = target.closest("[data-flip]"))) {
    found.setAttribute("aria-pressed", String(found.getAttribute("aria-pressed") !== "true"));
  } else if ((found = target.closest("[data-focus]"))) {
    var field = document.querySelector(found.dataset.focus);
    field.scrollIntoView({ behavior: "smooth", block: "center" });
    field.focus({ preventScroll: true });
  } else if ((found = target.closest("[data-reply-to]"))) {
    var turn = latestQuestion();
    if (turn) {
      turn.scrollIntoView({ behavior: "smooth", block: "center" });
      flash(turn);
    }
  } else if ((found = target.closest("[data-date]"))) {
    var input = document.getElementById(found.dataset.dateFor);
    input.value = localDay(Number(found.dataset.date), input);
    input.dispatchEvent(new Event("change", { bubbles: true }));
  } else if ((found = target.closest("[data-show-password]"))) {
    var key = document.getElementById(found.dataset.showPassword);
    var show = key.type === "password";
    key.type = show ? "text" : "password";
    found.setAttribute("aria-pressed", String(show));
    found.setAttribute("aria-label", show ? "Hide the key" : "Show the key");
    key.focus();
  } else if ((found = target.closest("[data-sort]"))) {
    sortTable(found.closest("th"));
  } else if ((found = target.closest("[data-confetti]"))) {
    burstFrom(found, 120);
  } else if ((found = target.closest(".stamp-large"))) {
    restamp(found);
  }
});

// Tickets on the home page lean toward the pointer.
var tilted = null;

function untilt(card) {
  if (card) {
    card.style.removeProperty("--rx");
    card.style.removeProperty("--ry");
  }
}

document.addEventListener("pointermove", function (event) {
  if (!finePointer.matches || reduceMotion.matches) {
    return;
  }
  var card = event.target.closest ? event.target.closest("[data-tilt]") : null;
  if (tilted !== card) {
    untilt(tilted);
    tilted = card;
  }
  if (!card) {
    return;
  }
  var box = card.getBoundingClientRect();
  var x = (event.clientX - box.left) / box.width;
  var y = (event.clientY - box.top) / box.height;
  card.style.setProperty("--rx", ((0.5 - y) * 9).toFixed(2) + "deg");
  card.style.setProperty("--ry", ((x - 0.5) * 11).toFixed(2) + "deg");
  card.style.setProperty("--gx", (x * 100).toFixed(1) + "%");
  card.style.setProperty("--gy", (y * 100).toFixed(1) + "%");
});

document.documentElement.addEventListener("pointerleave", function () {
  untilt(tilted);
  tilted = null;
});

// Keyboard: "/" finds the main text box, "?" lists shortcuts, "b" rings, Cmd/Ctrl+Enter sends.
document.addEventListener("keydown", function (event) {
  var typingInField = event.target.closest && event.target.closest("input, textarea, select, [contenteditable]");
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter" && typingInField && event.target.form) {
    event.preventDefault();
    event.target.form.requestSubmit();
    return;
  }
  if (typingInField || event.metaKey || event.ctrlKey || event.altKey || document.querySelector("dialog[open]")) {
    return;
  }
  if (event.key === "/") {
    var main = document.querySelector("[data-main-input]");
    if (main) {
      event.preventDefault();
      main.scrollIntoView({ behavior: "smooth", block: "center" });
      main.focus({ preventScroll: true });
    }
  } else if (event.key === "?") {
    openDialog("shortcuts");
  } else if (event.key === "b" || event.key === "B") {
    var bell = document.querySelector("[data-bell]");
    if (bell) {
      ring(bell);
    }
  }
});

// hx-confirm opens the kitchen's own dialog instead of the browser's.
document.addEventListener("htmx:confirm", function (event) {
  var dialog = document.getElementById("confirm-dialog");
  if (!event.detail.question || !dialog || !dialog.showModal) {
    return;
  }
  event.preventDefault();
  dialog.querySelector("[data-confirm-text]").textContent = event.detail.question;
  dialog.querySelector("[data-confirm-yes]").textContent = event.detail.elt.getAttribute("data-confirm-yes") || "Yes";
  dialog.returnValue = "";
  dialog.addEventListener(
    "close",
    function () {
      if (dialog.returnValue === "ok") {
        event.detail.issueRequest(true);
      }
    },
    { once: true }
  );
  dialog.showModal();
});

// A thin progress bar while any request is out.
var root = document.documentElement;

document.addEventListener("htmx:beforeRequest", function (event) {
  if (!event.defaultPrevented) {
    root.classList.remove("is-loaded");
    root.classList.add("is-loading");
  }
});

function finishLoading() {
  if (!root.classList.contains("is-loading")) {
    return;
  }
  root.classList.remove("is-loading");
  root.classList.add("is-loaded");
  setTimeout(function () {
    root.classList.remove("is-loaded");
  }, 600);
}

document.addEventListener("htmx:afterRequest", finishLoading);
document.addEventListener("htmx:sendError", function () {
  finishLoading();
  toast("Couldn't reach the kitchen. Check your connection and try again.", "error");
});
