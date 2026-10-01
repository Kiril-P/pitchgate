// Chef takes a few seconds per round. Lock the form and show who is busy.
document.addEventListener("submit", function (event) {
  var form = event.target;
  if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) {
    event.preventDefault();
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

var latest = document.querySelectorAll(".thread .message.chef");
if (latest.length > 1) {
  latest[latest.length - 1].scrollIntoView({ block: "center" });
}
