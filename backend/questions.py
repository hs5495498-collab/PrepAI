"""Sample/demo question bank, mirroring prepai/js/data.js's P.demoQuestions.
Clearly sample data for this prototype phase - no real AI is involved."""

DEMO_QUESTION_BANK = {
    "technical": [
        ("easy", "What is the difference between a list/array and a tuple, and when would you use each?"),
        ("easy", "What does API stand for, and what problem does it solve?"),
        ("medium", "Explain the difference between == and === (or similar value vs strict equality) in a language you know."),
        ("medium", "What is a database index, and why does it speed up queries?"),
        ("hard", "How would you design a simple rate limiter for an API?"),
        ("hard", "Explain how a hash table resolves collisions."),
    ],
    "hr": [
        ("easy", "Tell me about yourself."),
        ("easy", "Why do you want to work here?"),
        ("medium", "What are your greatest strengths and weaknesses?"),
        ("medium", "Where do you see yourself in five years?"),
        ("hard", "Why should we hire you over other candidates?"),
        ("hard", "Describe a time you received difficult feedback. How did you respond?"),
    ],
    "behavioral": [
        ("easy", "Describe a time you worked as part of a team."),
        ("easy", "Tell me about a goal you set and how you achieved it."),
        ("medium", "Tell me about a time you disagreed with a teammate and how you resolved it."),
        ("medium", "Describe a situation where you had to meet a tight deadline."),
        ("hard", "Tell me about a time you failed. What did you learn?"),
        ("hard", "Describe a time you had to persuade someone who disagreed with you."),
    ],
}


def pick_questions(category: str, difficulty: str, count: int):
    """Returns a list of (question_id, text) tuples for a new session.
    Falls back to the full category pool if nothing matches the requested
    difficulty, then cycles through the pool if count exceeds its size -
    same fallback behaviour as the frontend's practice.html setup."""
    pool = [text for d, text in DEMO_QUESTION_BANK[category] if d == difficulty]
    if not pool:
        pool = [text for _, text in DEMO_QUESTION_BANK[category]]
    selected = [pool[i % len(pool)] for i in range(count)]
    return [(f"q{i + 1}", text) for i, text in enumerate(selected)]
