PACK = {
    "problem": "Students lose money selling textbooks back to the campus store.",
    "first_customer": "BBA students who sell books at the end of each term",
    "assumptions": ["Buyers will pay a small listing fee"],
    "mvp": [{"feature": "List a book", "why": "Marta waited three weeks to sell hers"}],
    "not_yet": ["Payments in the app"],
    "user_stories": ["As a seller, I want to list a book, so that a buyer finds it before term"],
    "screens": ["Listing form"],
    "data_model": [{"table": "books", "fields": "id, title, course, price"}],
    "stack": "Flask and SQLite",
    "tasks": ["Create the Flask app", "Add the books table"],
    "claude_prompt": "Build a small Flask app where students list textbooks for next term's courses.",
}
