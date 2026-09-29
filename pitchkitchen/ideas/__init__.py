"""Idea domain: everything the founder wrote, stored as a tree of revisions.

The pitch is the root. Each answer is a child of the revision before it.
Verdict labels do not belong here. `logic.py` checks the text and walks branches. `store.py` writes SQLite.
"""
