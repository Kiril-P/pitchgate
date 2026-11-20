// One idea's page. The markup lives in idea.html; this file fills it from GET /ideas/<token>
// on the ideas service. Every action answers with the whole page again, so render() is the
// only way the page changes. With review unreachable, the founder's own text still shows.

var main = document.getElementById("main");
var token = new URLSearchParams(location.search).get("t") || "";
var path = "/ideas/" + encodeURIComponent(token);
var page = null;
var foundFacts = [];

var GATE_ICONS = { PASSED: "check", SENT_BACK: "rotate", PENDING: "clock" };
var GATE_NAMES = { PASSED: "Passed", SENT_BACK: "Sent back", PENDING: "Not scored" };

function $(selector, root) {
  return (root || main).querySelector(selector);
}

function setText(selector, value, root) {
  $(selector, root).textContent = value;
}

function show(selector, visible, root) {
  $(selector, root).hidden = !visible;
}

function clone(id) {
  return document.getElementById(id).content.firstElementChild.cloneNode(true);
}

function fillList(selector, items, build) {
  var list = $(selector);
  list.replaceChildren.apply(list, items.map(build));
}

function setTime(element, timestamp, style) {
  element.setAttribute("datetime", timestamp);
  element.dataset.time = style || "stamp";
  element.textContent = timestamp.slice(0, 10);
}

function setLabel(element, verdict, kind) {
  var label = labelOf(verdict);
  element.className = kind + " " + kind + "-" + label.toLowerCase();
  element.textContent = label;
  if (kind === "chip") {
    element.dataset.tip = LABEL_TIPS[label];
  }
}

function setLink(element, url) {
  element.href = /^https?:\/\//i.test(url || "") ? url : "#";
}

function checkItem(text) {
  var item = clone("t-check");
  item.querySelector("span").textContent = text;
  return item;
}

function scoreBar(name, value, maximum, cutoff, shown, note, invert) {
  var item = clone("t-bar");
  var passed = invert ? value <= cutoff : value >= cutoff;
  item.className = "bar " + (passed ? "bar-pass" : "bar-miss") + (invert ? " bar-invert" : "");
  setText("[data-name]", name, item);
  setText("[data-shown]", shown, item);
  $(".bar-track", item).dataset.tip = note;
  $(".bar-fill", item).style.setProperty("--w", (value / maximum) * 100 + "%");
  $(".bar-cutoff", item).style.left = (cutoff / maximum) * 100 + "%";
  return item;
}

function bandBar(name, value, shown) {
  return scoreBar(name, value, 3, 2.0, shown, "Solid or better is needed for PROVEN");
}

function station(item, index) {
  var li = clone("t-station");
  li.classList.add("station-" + item.state);
  if (item.state === "current") {
    li.setAttribute("aria-current", "step");
  }
  setText(".station-number", pad(index + 1), li);
  $(".station-icon use", li).setAttribute("href", "#i-" + (item.state === "done" ? "check" : STATION_ICONS[item.key]));
  setText(".station-name", item.name, li);
  setText(".station-job", item.job, li);
  return li;
}

function renderHead(idea, review, head) {
  $("[data-share]").classList.toggle("is-on", idea.shared);
  $("[data-share]").setAttribute("aria-pressed", String(idea.shared));
  setText("[data-share-label]", idea.shared ? "Stop sharing" : "Share on cohort board");
  show("[data-review-down]", !review);
  fillList("[data-stations]", page.stations, station);
  setText("[data-meta]", "#" + pad3(idea.id) + " · " + idea.display_name + " · " + idea.status + (review ? " · session " + review.sessions : ""));
  setText("[data-created]", idea.created_at.slice(0, 10));
  setText("[data-one-liner]", page.branch[0].one_liner);
  setLabel($("[data-stamp]"), head.verdict, "stamp");
  $("[data-stamp]").classList.add("stamp-large");
  show("[data-shared-note]", idea.shared);
  show("[data-pivot]", Boolean(page.pivot_from));
  if (page.pivot_from) {
    $("[data-pivot-link]").href = "idea.html?t=" + encodeURIComponent(page.pivot_from.token);
    setText("[data-pivot-link]", "“" + page.pivot_from.one_liner + "”");
  }
}

function renderEvidence(verdict, review) {
  show("[data-evidence]", Boolean(review));
  if (!review) {
    return;
  }
  var spent = review.jev_used >= review.jev_budget;
  $("[data-gauge]").classList.toggle("gauge-spent", spent);
  $("[data-gauge]").style.setProperty("--p", Math.min(review.jev_budget ? (review.jev_used / review.jev_budget) * 100 : 100, 100));
  $("[data-budget]").classList.toggle("budget-spent", spent);
  setText("[data-budget]", "Jev " + review.jev_used + " / " + review.jev_budget);
  var scored = Boolean(verdict && verdict.market_need !== null);
  show("[data-scored]", scored);
  show("[data-unscored]", !scored);
  if (!scored) {
    setText("[data-unscored-why]", verdict ? verdict.explanation : "Nothing has been sent to Jev for this version.");
    return;
  }
  setText("[data-explanation]", verdict.explanation);
  var bars = [
    bandBar("Market need", verdict.market_need, verdict.market_need_band),
    bandBar("Feasibility", verdict.feasibility, verdict.feasibility_band),
    bandBar("Differentiation", verdict.differentiation, verdict.differentiation_band),
  ];
  if (verdict.evidence !== null) {
    bars.push(bandBar("Facts in your latest message", verdict.evidence, verdict.evidence_band));
  }
  bars.push(scoreBar("Safety risk", verdict.safety_risk, 1, 0.5, verdict.safety_risk > 0.5 ? "High" : "Low", "Above the mark is an automatic UNPROVEN", true));
  $("[data-bars]").replaceChildren.apply($("[data-bars]"), bars);
  show("[data-answered]", verdict.answered !== null);
  if (verdict.answered !== null) {
    var yes = verdict.answered >= 0.5;
    $("[data-answered-value]").className = "answered answered-" + (yes ? "yes" : "no");
    setText("[data-answered-value]", yes ? "yes" : "no");
  }
}

function founderMessage(revision) {
  var li = clone("t-founder");
  setText("[data-initial]", page.idea.display_name.slice(0, 1).toUpperCase(), li);
  setText("[data-name]", page.idea.display_name, li);
  setTime($("[data-when]", li), revision.created_at);
  show("[data-edited]", revision.versions > 0, li);
  if (page.review) {
    setLabel($("[data-chip]", li), revision.verdict, "chip");
  }
  var pitch = revision.kind === "pitch";
  show("[data-title]", pitch, li);
  setText("[data-title]", revision.one_liner || "", li);
  setText("[data-text]", pitch ? revision.story : revision.answer, li);
  if (!pitch && !page.closed) {
    show("[data-edit]", true, li);
    $("form", li).dataset.revision = revision.id;
    $("textarea", li).value = revision.answer;
  }
  return li;
}

function chefMessage(revision) {
  var li = clone("t-chef");
  var turn = revision.chef;
  setTime($("[data-when]", li), turn.created_at, "clock");
  show("[data-question]", Boolean(turn.question), li);
  setText("[data-question]", turn.question || "", li);
  setText("[data-reaction]", turn.body, li);
  var verdict = revision.verdict;
  var note = verdict && verdict.recommendation && verdict.label !== "PROVEN";
  show("[data-note]", Boolean(note), li);
  setText("[data-note-text]", note ? verdict.recommendation : "", li);
  return li;
}

function renderThread(review, head) {
  var items = [];
  page.branch.forEach(function (revision) {
    items.push(founderMessage(revision));
    if (revision.chef) {
      items.push(chefMessage(revision));
    }
  });
  if (review && review.paused && !page.closed) {
    var paused = clone("t-paused");
    var jev = review.paused === "jev";
    setText("[data-why]", jev ? "Jev didn't score this one yet." : "Chef stepped out. Your answer is saved.", paused);
    setText("[data-detail]", jev && head.verdict ? head.verdict.explanation : "", paused);
    items.push(paused);
  } else if (review && review.step === "open" && !page.closed && head.chef && !head.chef.question) {
    var opener = clone("t-opener");
    setText("[data-meta]", "Kitchen · session " + review.sessions, opener);
    setText(
      "[data-question]",
      "Session " + review.sessions + " is open. What did your facts and conversations teach you: what surprised you, and what do people already do or pay about it today?",
      opener
    );
    items.push(opener);
  }
  $("[data-thread]").replaceChildren.apply($("[data-thread]"), items);
}

function renderGrill(idea, review, head) {
  var open = Boolean(review && review.step === "open" && !page.closed);
  var pips = [];
  for (var n = 0; open && n < review.session_answers; n++) {
    var pip = document.createElement("i");
    pip.className = n < review.session_answers - review.answers_left ? "on" : "";
    pips.push(pip);
  }
  $("[data-pips]").replaceChildren.apply($("[data-pips]"), pips);
  setText("[data-answer-count]", plural(page.branch.length - 1, "answer") + (open ? " · " + review.answers_left + " left this session" : ""));
  renderThread(review, head);

  show("[data-binned]", idea.status === "binned");
  $("[data-pivot-this]").href = "index.html?pivot=" + encodeURIComponent(idea.token);
  renderServed(idea, review);

  var cooking = review && !page.closed;
  var spent = cooking && review.jev_used >= review.jev_budget;
  show("[data-budget-spent]", spent);
  if (spent) {
    setText(
      "[data-budget-spent-text]",
      "This idea has used its whole Jev budget (" + review.jev_budget + " scores), so new answers and gates won't be scored. You can still log facts and conversations and write your starter pack."
    );
  }
  show("form[data-action=answer]", cooking && !spent && review.step === "open" && !review.paused);
  if (cooking) {
    $("#answer-box").placeholder =
      head.chef && !head.chef.question ? "Session " + review.sessions + ": tell Chef what the conversations taught you." : "Names, dates, numbers: things that already happened.";
  }
  show("[data-homework-due]", cooking && !spent && review.step === "homework");
  if (cooking) {
    setText("[data-homework-due-text]", "Session " + review.sessions + " is over. Do the homework below and log what people told you to open session " + (review.sessions + 1) + ".");
  }

  show("[data-actions]", cooking);
  if (cooking) {
    var proven = !review.servable && head.verdict && head.verdict.label === "PROVEN";
    show("form[data-action=serve]", review.servable);
    show("[data-proven-note]", proven);
    setText("[data-proven-note]", proven ? "PROVEN in the interview. Log " + plural(review.serve_min_logs - page.talks, "more real conversation") + " to serve it." : "");
    show("[data-parked]", idea.status === "parked");
    show("form[data-action=park]", idea.status !== "parked");
  }
}

function renderServed(idea, review) {
  var served = idea.status === "served";
  show("[data-served]", served);
  $("[data-served]").dataset.celebrate = "served-" + idea.token;
  if (!served || !review) {
    return;
  }
  show("[data-polished-wrap]", Boolean(review.polished));
  $("#polished").textContent = review.polished ? review.polished.body : "";
  var steps = (review.next_steps && review.next_steps.body) || [];
  show("[data-next-steps]", steps.length > 0);
  $("[data-steps]").dataset.checklist = "steps-" + idea.token;
  fillList("[data-steps]", steps, checkItem);
}

function logItem(entry) {
  var fact = entry.kind === "fact";
  var li = clone(fact ? "t-fact-log" : "t-log");
  setText("[data-day]", (fact ? "Fact · " : "") + entry.spoken_on, li);
  setText("[data-session]", "session " + entry.session, li);
  if (fact) {
    setText("[data-quote]", entry.quote, li);
    setLink($("[data-source]", li), entry.source);
    setText("[data-site]", entry.who, li);
    return li;
  }
  setText("[data-initial]", entry.who.slice(0, 1).toUpperCase(), li);
  setText("[data-who]", entry.who, li);
  setText("[data-role]", entry.role ? ", " + entry.role : "", li);
  setText("[data-quote]", "“" + entry.quote + "”", li);
  show("[data-today]", Boolean(entry.today_they), li);
  setText("[data-today]", "Does today: " + entry.today_they, li);
  show("[data-paid]", Boolean(entry.paid), li);
  setText("[data-paid]", "Pays today: " + entry.paid, li);
  return li;
}

function renderGate(gate, idea) {
  var latest = gate && gate.latest;
  show("[data-gate]", Boolean(latest));
  if (!latest) {
    return;
  }
  var block = $("[data-gate]");
  block.className = "gate gate-" + latest.label.toLowerCase();
  if (latest.label === "PASSED") {
    block.dataset.celebrate = "gate-" + idea.token + "-" + latest.session;
  } else {
    delete block.dataset.celebrate;
  }
  $("[data-gate-icon]").setAttribute("href", "#i-" + GATE_ICONS[latest.label]);
  setText("[data-gate-title]", "Gate, session " + latest.session + ": " + GATE_NAMES[latest.label]);
  setText("[data-gate-explanation]", latest.explanation);
  var bars =
    latest.evidence_strength === null
      ? []
      : [
          bandBar("Evidence strength", latest.evidence_strength, latest.evidence_strength_band),
          bandBar("How often it hurts", latest.pain_frequency, latest.pain_frequency_band),
          bandBar("Already paying for it", latest.willingness_to_pay, latest.willingness_to_pay_band),
        ];
  $("[data-gate-bars]").replaceChildren.apply($("[data-gate-bars]"), bars);
}

function renderTasting(idea, review) {
  show("[data-tasting]", idea.status !== "binned");
  var open = Boolean(review && !page.closed);
  main.querySelectorAll("[data-tasting-open]").forEach(function (part) {
    part.hidden = !open;
  });
  setText("[data-tasting-counts]", (review ? review.gate.logs.length + " logged this session · " : "") + plural(page.talks, "talk") + " · " + plural(page.facts, "fact"));
  renderGate(review && review.gate, idea);
  fillList("[data-logs]", page.evidence.slice().reverse(), logItem);
  if (!open) {
    return;
  }
  var homework = review.homework;
  show("[data-homework]", Boolean(homework));
  show("[data-starter-intro]", !homework && review.starter_gate);
  show("[data-gate-intro]", !homework && !review.starter_gate);
  if (homework) {
    $("[data-people]").dataset.checklist = "people-" + idea.token + "-" + review.sessions;
    fillList("[data-people]", homework.people, checkItem);
    fillList("[data-questions]", homework.questions, function (question) {
      var item = clone("t-question");
      item.querySelector("span").textContent = question;
      return item;
    });
  }
  var day = today();
  var date = $("#spoken-on");
  date.max = day;
  date.value = date.value || day;
  $(".fact-form [name=spoken_on]").value = day;

  var gate = review.gate;
  var plates = [];
  for (var n = 0; n < 3; n++) {
    var plate = document.createElement("i");
    plate.className = n < gate.logs.length ? "on" : "";
    plate.innerHTML = icon("check");
    plates.push(plate);
  }
  $("[data-plates]").replaceChildren.apply($("[data-plates]"), plates);
  show("form[data-action=gate]", gate.ready);
  setText(
    "[data-gate-hint]",
    gate.ready
      ? ""
      : gate.logs.length < 3
      ? 3 - gate.logs.length + " more this session to ask for the gate." + (review.starter_gate ? " Facts count." : "")
      : "Log a new conversation to try the gate again."
  );
}

function renderPack(idea, review) {
  show("[data-pack]", Boolean(review));
  if (!review) {
    return;
  }
  var verified = idea.status === "served";
  var pack = review.pack;
  $("[data-pack-badge]").className = "pack-badge pack-badge-" + (verified ? "verified" : "draft");
  setText("[data-pack-badge]", verified ? "Verified" : "Draft");
  setText(
    "[data-pack-intro]",
    verified
      ? "Served with " + plural(page.talks, "real conversation") + " behind it. Take it into Claude Code and build version one."
      : "One Markdown file to start building with Claude Code: the problem, your evidence with its sources, what to build first, and every assumption still to test. It becomes verified when this idea is served."
  );
  show("[data-pack-written]", Boolean(pack));
  show("[data-download]", Boolean(pack));
  $("[data-pack-button]").className = pack ? "secondary" : "primary";
  setText("[data-pack-button] [data-label]", pack ? "Rewrite it" : "Write my starter pack");
  if (!pack) {
    return;
  }
  fillList("[data-mvp]", pack.mvp, function (item) {
    var li = document.createElement("li");
    var name = document.createElement("strong");
    name.textContent = item.feature + ".";
    li.append(name, " " + item.why);
    return li;
  });
  fillList("[data-tasks]", pack.tasks.slice(0, 4), function (task) {
    var li = document.createElement("li");
    li.textContent = task;
    return li;
  });
  $("#claude-prompt").textContent = pack.claude_prompt;
  show("[data-pack-stale]", review.pack_stale);
}

function render(found, anchor) {
  page = found;
  var idea = page.idea;
  var review = page.review;
  var head = page.branch[page.branch.length - 1];
  document.title = idea.display_name + " · Pitch Kitchen";
  main.className = "idea tone-" + idea.tone;
  $("[data-state]").hidden = true;
  $("[data-page]").hidden = false;
  renderHead(idea, review, head);
  renderEvidence(head.verdict, review);
  renderGrill(idea, review, head);
  renderTasting(idea, review);
  renderPack(idea, review);
  setUp(main);
  scrollToAnchor(anchor);
}

function scrollToAnchor(anchor) {
  var target = null;
  if (anchor === "turn") {
    var turns = main.querySelectorAll(".thread .message.chef");
    target = turns.length > 1 ? turns[turns.length - 1] : null;
  } else if (anchor) {
    target = document.getElementById(anchor);
  }
  if (target) {
    target.scrollIntoView({ behavior: "smooth", block: anchor === "turn" ? "center" : "start" });
  }
}

function load() {
  var state = $("[data-state]");
  state.hidden = false;
  $("[data-page]").hidden = true;
  if (!token) {
    failed(state, { message: "This link has no idea in it. Open one from your ideas." }, function () {
      location.href = "index.html";
    });
    return;
  }
  loading(state, "Fetching the ticket…");
  api
    .ideas(path)
    .then(function (found) {
      render(found, location.hash.slice(1) || null);
    })
    .catch(function (error) {
      if (error.status === 404) {
        forgetToken(token);
      }
      failed(state, error, load);
    });
}

// The founder's answer and Chef's typing dots show at once; the real page replaces them.
function showPendingTurn(form) {
  var founder = clone("t-founder");
  setText("[data-initial]", page.idea.display_name.slice(0, 1).toUpperCase(), founder);
  setText("[data-name]", page.idea.display_name, founder);
  setText("[data-text]", form.elements.answer.value, founder);
  var chef = clone("t-chef");
  $(".bubble", chef).className = "bubble typing";
  $(".bubble", chef).innerHTML = "<span></span><span></span><span></span>";
  founder.dataset.pending = chef.dataset.pending = "yes";
  $("[data-thread]").append(founder, chef);
  form.elements.answer.readOnly = true;
  chef.scrollIntoView({ behavior: "smooth", block: "center" });
}

function dropPendingTurn(form) {
  main.querySelectorAll("[data-pending]").forEach(function (item) {
    item.remove();
  });
  form.elements.answer.readOnly = false;
}

function evidenceFields(form) {
  var fields = {};
  ["kind", "who", "role", "spoken_on", "today_they", "paid", "quote", "source"].forEach(function (name) {
    if (form.elements[name]) {
      fields[name] = form.elements[name].value;
    }
  });
  return fields;
}

// What each form does: which ideas endpoint it calls, with what, and where the page scrolls after.
var ACTIONS = {
  answer: function (form) {
    return { path: "/answers", body: { answer: form.elements.answer.value }, slow: true, anchor: "turn", pending: true };
  },
  edit: function (form) {
    return { path: "/answers/" + form.dataset.revision, body: { answer: form.elements.answer.value }, slow: true, anchor: "turn" };
  },
  retry: function () {
    return { path: "/retry", slow: true, anchor: "turn" };
  },
  evidence: function (form) {
    return { path: "/evidence", body: evidenceFields(form), anchor: "tasting" };
  },
  "keep-facts": function (form) {
    var picked = Array.prototype.slice.call(form.querySelectorAll("input[name=keep]:checked")).map(function (box) {
      var fact = foundFacts[Number(box.value)];
      return { quote: fact.fact, source: fact.source, who: fact.site || "" };
    });
    return { path: "/facts", body: { facts: picked }, anchor: "tasting", done: hideFacts };
  },
  gate: function () {
    return { path: "/gate", slow: true, anchor: "tasting" };
  },
  serve: function () {
    return { path: "/serve", slow: true };
  },
  pack: function () {
    return { path: "/pack", slow: true, anchor: "pack", errorSlot: "[data-pack-error]" };
  },
  share: function () {
    return { path: "/share" };
  },
  park: function () {
    return { path: "/park", home: true };
  },
};

main.addEventListener("submit", function (event) {
  var form = event.target.closest("form[data-action]");
  if (!form) {
    return;
  }
  event.preventDefault();
  if (form.dataset.action === "delete") {
    deleteIdea();
    return;
  }
  if (!form.reportValidity()) {
    return;
  }
  clearError(form);
  var action = ACTIONS[form.dataset.action](form);
  busy(form, function () {
    if (action.pending) {
      showPendingTurn(form);
    }
    return api
      .ideas(path + action.path, { method: "POST", body: action.body || {}, slow: action.slow })
      .then(function (found) {
        if (action.home) {
          location.href = "index.html";
          return;
        }
        clearDrafts(form);
        form.reset();
        if (action.pending) {
          form.elements.answer.readOnly = false;
        }
        if (action.done) {
          action.done();
        }
        render(found, action.anchor);
      })
      .catch(function (error) {
        if (action.pending) {
          dropPendingTurn(form);
        }
        var slot = action.errorSlot && $(action.errorSlot);
        if (slot) {
          slot.textContent = error.message;
          slot.hidden = false;
        } else {
          showError(form, error);
        }
      });
  });
});

// Delete goes to the ideas service, which asks review to forget its scores first.
function deleteIdea() {
  confirmAction("Delete this idea, its conversation, and its logs?", "Delete idea").then(function (yes) {
    if (!yes) {
      return;
    }
    api
      .ideas(path, { method: "DELETE" })
      .then(function () {
        forgetToken(token);
        location.href = "index.html";
      })
      .catch(function (error) {
        toast(error.message, "error");
      });
  });
}

function hideFacts() {
  show("[data-facts-error]", false);
  show("[data-look-ups]", false);
  show("form[data-action=keep-facts]", false);
}

function showFacts(found) {
  hideFacts();
  if (found.searches && found.searches.length) {
    fillList("[data-look-up-list]", found.searches, function (search) {
      var li = clone("t-look-up");
      setText("[data-find]", search.find, li);
      setText("[data-query]", search.query, li);
      $("[data-link]", li).href = "https://www.google.com/search?q=" + encodeURIComponent(search.query);
      return li;
    });
    show("[data-look-ups]", true);
  } else if (found.facts.length) {
    foundFacts = found.facts;
    fillList("[data-fact-list]", found.facts, function (fact, index) {
      var pick = clone("t-fact-pick");
      $("input", pick).value = index;
      setText("[data-fact]", fact.fact, pick);
      setLink($("[data-source]", pick), fact.source);
      setText("[data-site]", fact.site || "Source", pick);
      return pick;
    });
    show("form[data-action=keep-facts]", true);
  } else {
    setText("[data-facts-error]", found.notice || "Chef found nothing this time. Try again, or add a fact you found yourself.");
    show("[data-facts-error]", true);
  }
}

function searchFacts(button) {
  var target = document.getElementById("facts");
  hideFacts();
  target.classList.add("is-working");
  button.disabled = true;
  api
    .ideas(path + "/facts/search", { method: "POST", body: {}, slow: true })
    .then(showFacts)
    .catch(function (error) {
      showFacts({ facts: [], notice: error.message });
    })
    .finally(function () {
      target.classList.remove("is-working");
      button.disabled = false;
    });
}

// The pack is fetched rather than linked, so a sleeping service gets a message instead of an error page.
function downloadPack(button) {
  button.disabled = true;
  startLoading();
  fetch(api.ideasUrl(path + "/starter-pack.md"))
    .then(function (response) {
      if (!response.ok) {
        throw new Error();
      }
      return response.blob();
    })
    .then(function (blob) {
      var link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = "starter-pack.md";
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(function () {
        URL.revokeObjectURL(link.href);
      }, 1000);
    })
    .catch(function () {
      toast("Couldn't download the starter pack. Try again in a moment.", "error");
    })
    .finally(function () {
      finishLoading();
      button.disabled = false;
    });
}

main.addEventListener("click", function (event) {
  var found;
  if ((found = event.target.closest("[data-search]"))) {
    searchFacts(found);
  } else if ((found = event.target.closest("[data-download]"))) {
    downloadPack(found);
  } else if (event.target.closest("[data-reload]")) {
    load();
  }
});

load();
