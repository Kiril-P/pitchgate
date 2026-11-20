// The home page: the pitch form, Chef's Prep suggestions (review service), and the boards (ideas service).

var form = document.getElementById("pitch-form");
var boardsArea = document.getElementById("boards");
var pivotToken = new URLSearchParams(location.search).get("pivot");

var EMPTY = {
  kitchen: ["flame", "Nothing cooking. Send an idea in."],
  served: ["cloche", "Nothing served yet."],
  binned: ["trash", "The bin is empty."],
};

function boardSection(key, title, glyph, ideas, emptyText, extra) {
  var body = ideas.length
    ? '<ul class="tickets">' + ideas.map(card).join("") + "</ul>"
    : '<div class="empty"><span class="empty-icon">' + icon(glyph) + "</span><p>" + esc(emptyText) + "</p>" + (extra || "") + "</div>";
  return (
    '<section class="board board-' + key + '" id="board-' + key + '">' +
    '<div class="section-head"><h2>' + icon(glyph) + esc(title) + "</h2><p>" + (key === "cohort" ? "Ideas other founders chose to share" : plural(ideas.length, "ticket")) + "</p></div>" +
    body + "</section>"
  );
}

function renderBoards(found) {
  var tabs = found.boards
    .map(function (board) {
      return '<a class="board-tab" href="#board-' + board.key + '">' + esc(board.title) + '<span class="count">' + board.ideas.length + "</span></a>";
    })
    .join("");
  var start = '<button class="secondary" type="button" data-focus="#display-name">' + icon("receipt") + "<span>Start a ticket</span></button>";
  boardsArea.innerHTML =
    notice(found.notice) +
    '<div class="boards-head"><h2 class="area-title">Your ideas</h2><nav class="board-tabs" aria-label="Boards">' + tabs +
    '<a class="board-tab" href="#board-cohort">Cohort<span class="count">' + found.cohort.length + "</span></a></nav></div>" +
    found.boards
      .map(function (board) {
        var empty = EMPTY[board.key];
        return boardSection(board.key, board.title, empty[0], board.ideas, empty[1], board.key === "kitchen" ? start : "");
      })
      .join("") +
    boardSection("cohort", "Cohort board", "users", found.cohort, "Nobody has shared an idea yet.");
  setUp(boardsArea);
}

function loadBoards() {
  loading(boardsArea, "Fetching your tickets…");
  api
    .ideas("/ideas?mine=" + encodeURIComponent(myTokens().join(",")))
    .then(renderBoards)
    .catch(function (error) {
      failed(boardsArea, error, loadBoards);
    });
}

// Pivoting opens the form filled in from the binned idea, which stays as it was.
function prefillPivot() {
  if (!pivotToken) {
    return;
  }
  api
    .ideas("/ideas/" + encodeURIComponent(pivotToken))
    .then(function (page) {
      var pitch = page.branch[0];
      form.elements.display_name.value = page.idea.display_name;
      form.elements.one_liner.value = pitch.one_liner;
      form.elements.story.value = pitch.story;
      form.elements.tone.value = page.idea.tone;
      form.elements.level.value = page.idea.level;
      ["display_name", "one_liner", "story"].forEach(function (name) {
        changed(form.elements[name]);
      });
      form.querySelector("[data-order-kind]").textContent = "Pivot";
      var note = form.querySelector("[data-pivot-note]");
      note.querySelector("span").textContent = "Pivoting from “" + pitch.one_liner + "”. The old idea stays as it is.";
      note.hidden = false;
    })
    .catch(function (error) {
      pivotToken = null;
      showError(form, error);
    });
}

function suggestionsHtml(suggestions) {
  return (
    '<p class="fine">Pick one to use it, then edit it if you like.</p>' +
    suggestions
      .map(function (suggestion, index) {
        return (
          '<button class="suggestion" type="button" data-fill="' + esc(suggestion.one_liner) + '"' +
          (suggestion.story ? ' data-story="' + esc(suggestion.story) + '"' : "") + ' style="--i: ' + index + '">' +
          '<span class="suggestion-number">' + (index + 1) + "</span>" +
          '<span class="suggestion-text"><span>' + esc(suggestion.one_liner) + "</span>" +
          (suggestion.first_fact ? '<span class="suggestion-fact">First fact to check: ' + esc(suggestion.first_fact) + "</span>" : "") +
          "</span></button>"
        );
      })
      .join("")
  );
}

// Chef's Prep suggestions come straight from the review service; ideas isn't involved.
function askChef(target, path, body, missing) {
  if (!Object.values(body)[0].trim()) {
    target.innerHTML = '<p class="error">' + esc(missing) + "</p>";
    return;
  }
  target.innerHTML = "";
  target.classList.add("is-working");
  api
    .review(path, { method: "POST", body: body, slow: true })
    .then(function (found) {
      target.innerHTML = suggestionsHtml(found.suggestions);
    })
    .catch(function (error) {
      target.innerHTML = '<p class="error">' + esc(error.message) + "</p>";
    })
    .finally(function () {
      target.classList.remove("is-working");
    });
}

form.querySelector("[data-spark]").addEventListener("click", function () {
  askChef(document.getElementById("sparks"), "/suggestions/sparks", { about: form.elements.about.value }, "Tell Chef a little about your week first.");
});

form.querySelector("[data-suggest]").addEventListener("click", function () {
  var rough = [form.elements.one_liner.value, form.elements.story.value].map(function (part) { return part.trim(); }).filter(Boolean).join(" ");
  askChef(document.getElementById("suggestions"), "/suggestions/one-liners", { text: rough }, "Write a rough idea or story first.");
});

form.addEventListener("submit", function (event) {
  event.preventDefault();
  if (!form.reportValidity()) {
    return;
  }
  clearError(form);
  var fields = form.elements;
  var body = {
    display_name: fields.display_name.value,
    one_liner: fields.one_liner.value,
    story: fields.story.value,
    tone: fields.tone.value,
    level: fields.level.value,
    shared: fields.shared.checked,
    consent: fields.consent.checked,
    pivot: pivotToken || "",
  };
  busy(form, function () {
    return api
      .ideas("/ideas", { method: "POST", body: body, slow: true })
      .then(function (page) {
        remember(page.idea.token);
        clearDrafts(form);
        location.href = "idea.html?t=" + encodeURIComponent(page.idea.token);
      })
      .catch(function (error) {
        showError(form, error);
      });
  });
});

prefillPivot();
loadBoards();
