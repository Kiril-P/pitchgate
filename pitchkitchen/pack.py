"""The starter pack: one Markdown file a founder takes into Claude Code.

Pure, like cohort: pitchkitchen/pages.py passes plain dicts in. The evidence section
is copied from the logs, never from Chef, so a pack can't cite a conversation or a
fact that was not logged. Chef's plan (review/coach.py write_starter_pack) fills the rest.
"""


def render_pack(one_liner, display_name, logs, plan, verified, made_on, needed=3):
    """needed: how many real conversations serving takes (review's SERVE_MIN_LOGS)."""
    talks = [entry for entry in logs if entry.get("kind", "conversation") == "conversation"]
    facts = [entry for entry in logs if entry.get("kind") == "fact"]
    lines = ["# Starter pack: " + one_liner, ""]
    if verified:
        lines.append("> **Verified.** Served on Pitch Kitchen with %d logged conversations behind it." % len(talks))
    else:
        lines.append(
            "> **Draft.** Not proven yet (%d of %d real conversations logged, not served). "
            "Build to learn, and treat every assumption below as a test." % (len(talks), needed)
        )
    lines += ["> Made for " + display_name + " on " + made_on + ".", ""]

    lines += ["## The problem", "", plan["problem"], ""]
    if plan["first_customer"]:
        lines += ["## First customer", "", plan["first_customer"], ""]

    lines += ["## Evidence", "", "### Conversations (%d)" % len(talks), ""]
    lines += [_talk(entry) for entry in talks] or ["None logged yet."]
    lines += ["", "### Facts found (%d)" % len(facts), ""]
    lines += ["- %s ([%s](%s), %s)" % (entry["quote"], entry["who"] or "source", entry["source"], entry["spoken_on"]) for entry in facts] or [
        "None logged yet."
    ]
    lines += ["", "### Still assumptions", ""]
    lines += _bullets(plan["assumptions"]) or ["None listed."]

    lines += ["", "## Version one", ""]
    lines += ["%d. **%s**: %s" % (number, item["feature"], item["why"]) for number, item in enumerate(plan["mvp"], 1)]
    for title, key in (("Not in version one", "not_yet"), ("User stories", "user_stories"), ("Screens", "screens")):
        if plan[key]:
            lines += ["", "## " + title, ""] + _bullets(plan[key])
    if plan["data_model"]:
        lines += ["", "## Data model", "", "| Table | Fields |", "|---|---|"]
        lines += ["| %s | %s |" % (item["table"], item["fields"].replace("|", "/")) for item in plan["data_model"]]
    if plan["stack"]:
        lines += ["", "## Stack", "", plan["stack"]]
    lines += ["", "## First tasks", ""]
    lines += ["%d. %s" % (number, task) for number, task in enumerate(plan["tasks"], 1)]

    lines += ["", "## CLAUDE.md", "", "Save this as `CLAUDE.md` in a new, empty repository.", "", "````markdown"]
    lines += claude_md(one_liner, plan)
    lines += ["````", "", "## First prompt for Claude Code", "", "Paste this as your first message.", "", "```text", plan["claude_prompt"], "```", ""]
    return "\n".join(lines)


def claude_md(one_liner, plan):
    lines = ["# " + one_liner, "", plan["problem"], ""]
    if plan["first_customer"]:
        lines += ["## Who it is for", "", plan["first_customer"], ""]
    lines += ["## Version one", ""] + ["- %s: %s" % (item["feature"], item["why"]) for item in plan["mvp"]]
    if plan["not_yet"]:
        lines += ["", "## Not in version one", ""] + _bullets(plan["not_yet"])
    if plan["stack"]:
        lines += ["", "## Stack", "", plan["stack"]]
    lines += [
        "",
        "## Working rules",
        "",
        "- Build only the version-one features; ask before adding anything else.",
        "- Each feature should serve a logged need or test an assumption from the starter pack.",
        "- Add a small test for each feature before starting the next one.",
    ]
    return lines


def _talk(entry):
    line = '- **%s**%s, %s: "%s"' % (entry["who"], ", " + entry["role"] if entry["role"] else "", entry["spoken_on"], entry["quote"])
    if entry.get("today_they"):
        line += " Does today: " + entry["today_they"].rstrip(".") + "."
    if entry.get("paid"):
        line += " Pays today: " + entry["paid"].rstrip(".") + "."
    return line


def _bullets(items):
    return ["- " + item for item in items]
