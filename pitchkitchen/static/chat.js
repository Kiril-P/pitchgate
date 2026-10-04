// htmx swaps the whole <body> after every form and link (hx-boost in base.html),
// so these listeners sit on the document and survive each swap.

// Forms inside the tasting panel come back to it after the redirect, because the
// "#tasting" in the redirect is lost when htmx follows it.
var returnTo = null;

// Chef takes a few seconds per round. Lock the form and show who is busy.
document.addEventListener("htmx:beforeRequest", function (event) {
  var form = event.detail.elt;
  if (form.tagName !== "FORM") {
    return;
  }
  returnTo = form.closest("#tasting") ? "tasting" : null;
  var button = form.querySelector("button[data-busy]");
  if (!button) {
    return;
  }
  if (form.dataset.sent) {
    event.preventDefault();
    return;
  }
  form.dataset.sent = "yes";
  var label = button.querySelector("[data-label]") || button;
  button.dataset.idle = label.textContent;
  label.textContent = button.dataset.busy;
  button.classList.add("busy");

  var thread = document.querySelector(".thread");
  var answer = form.querySelector("textarea[name=answer]");
  if (!thread || !answer) {
    return;
  }
  var initial = thread.querySelector(".avatar-founder");
  thread.insertAdjacentHTML(
    "beforeend",
    '<li class="message founder" data-pending><span class="avatar avatar-founder" aria-hidden="true"></span>' +
      '<div class="message-body"><div class="bubble"><p></p></div></div></li>' +
      '<li class="message chef" data-pending><span class="avatar avatar-chef" aria-hidden="true"><svg class="icon"><use href="#i-chef"></use></svg></span>' +
      '<div class="message-body"><div class="message-meta"><span>Chef</span></div>' +
      '<div class="bubble typing"><span></span><span></span><span></span></div></div></li>'
  );
  var sent = thread.querySelector(".message.founder[data-pending]");
  sent.querySelector(".bubble p").textContent = answer.value;
  sent.querySelector(".avatar").textContent = initial ? initial.textContent : "";
  answer.readOnly = true;
  thread.lastElementChild.scrollIntoView({ behavior: "smooth", block: "center" });
});

// The request never reached the server: give the form back so the founder can try again.
function unlock(event) {
  var form = event.detail.elt;
  if (!form || form.tagName !== "FORM") {
    return;
  }
  delete form.dataset.sent;
  var button = form.querySelector("button[data-busy]");
  if (button && button.dataset.idle) {
    (button.querySelector("[data-label]") || button).textContent = button.dataset.idle;
    button.classList.remove("busy");
  }
  var answer = form.querySelector("textarea[name=answer]");
  if (answer) {
    answer.readOnly = false;
  }
  document.querySelectorAll(".thread [data-pending]").forEach(function (item) {
    item.remove();
  });
}

document.addEventListener("htmx:sendError", unlock);
document.addEventListener("htmx:timeout", unlock);

function showLatestTurn(behavior) {
  var anchor = document.getElementById(returnTo || location.hash.slice(1));
  returnTo = null;
  if (anchor) {
    anchor.scrollIntoView({ behavior: behavior, block: "start" });
    return;
  }
  var latest = document.querySelectorAll(".thread .message.chef");
  if (latest.length > 1) {
    latest[latest.length - 1].scrollIntoView({ behavior: behavior, block: "center" });
  } else {
    window.scrollTo({ top: 0, behavior: behavior });
  }
}

document.addEventListener("DOMContentLoaded", function () {
  showLatestTurn("instant");
});

// Only whole-page swaps move the scroll; the Prep suggestions swap a small box.
document.addEventListener("htmx:afterSettle", function (event) {
  if (event.detail.elt === document.body) {
    showLatestTurn("smooth");
  }
});
