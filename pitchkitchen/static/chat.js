// htmx swaps the whole <body> after every form and link (hx-boost in base.html),
// so these listeners sit on the document and survive each swap.

// Chef takes a few seconds per round. Lock the form and show who is busy.
document.addEventListener("htmx:beforeRequest", function (event) {
  var form = event.detail.elt;
  if (form.tagName !== "FORM") {
    return;
  }
  var button = form.querySelector("button[data-busy]");
  if (!button) {
    return;
  }
  if (form.dataset.sent) {
    event.preventDefault();
    return;
  }
  form.dataset.sent = "yes";
  button.textContent = button.dataset.busy;
  button.classList.add("busy");

  var thread = document.querySelector(".thread");
  var answer = form.querySelector("textarea[name=answer]");
  if (!thread || !answer) {
    return;
  }
  thread.insertAdjacentHTML(
    "beforeend",
    '<li class="message founder"><div class="bubble"><p></p></div></li>' +
      '<li class="message chef"><div class="message-meta"><span>Chef</span></div>' +
      '<div class="bubble typing"><span></span><span></span><span></span></div></li>'
  );
  var sent = thread.querySelectorAll(".message.founder .bubble p");
  sent[sent.length - 1].textContent = answer.value;
  answer.readOnly = true;
  thread.lastElementChild.scrollIntoView({ behavior: "smooth", block: "center" });
});

// Prep: clicking one of Chef's suggested one-liners puts it in the field to edit.
document.addEventListener("click", function (event) {
  var choice = event.target.closest("[data-fill]");
  if (!choice) {
    return;
  }
  var input = document.getElementById("one-liner");
  input.value = choice.dataset.fill;
  input.focus();
});

function showLatestTurn(behavior) {
  var latest = document.querySelectorAll(".thread .message.chef");
  if (latest.length > 1) {
    latest[latest.length - 1].scrollIntoView({ behavior: behavior, block: "center" });
  } else {
    window.scrollTo({ top: 0 });
  }
}

document.addEventListener("DOMContentLoaded", function () {
  showLatestTurn("auto");
});

document.addEventListener("htmx:afterSettle", function () {
  showLatestTurn("smooth");
});
