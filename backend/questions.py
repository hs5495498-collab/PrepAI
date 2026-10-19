"""Sample/demo question bank, mirroring prepai/js/data.js's P.demoQuestions.
Clearly sample data for this prototype phase - no real AI is involved.

Each category has 5 distinct questions per difficulty (15 per category),
so a request for up to 15 questions (the schema's max, see
InterviewCreateRequest.question_count) can always be filled with that many
*distinct* questions - see pick_questions() below."""

DEMO_QUESTION_BANK = {
    "technical": [
        ("easy", "What is the difference between a list/array and a tuple, and when would you use each?"),
        ("easy", "What does API stand for, and what problem does it solve?"),
        ("easy", "What is version control, and why is it useful on a team?"),
        ("easy", "What is the difference between a compiler and an interpreter?"),
        ("easy", "What is a REST API?"),
        ("medium", "Explain the difference between == and === (or similar value vs strict equality) in a language you know."),
        ("medium", "What is a database index, and why does it speed up queries?"),
        ("medium", "What is the difference between synchronous and asynchronous code?"),
        ("medium", "Explain how garbage collection works in a language you know."),
        ("medium", "What is dependency injection, and why is it useful?"),
        ("hard", "How would you design a simple rate limiter for an API?"),
        ("hard", "Explain how a hash table resolves collisions."),
        ("hard", "How would you design a URL-shortening service?"),
        ("hard", "Explain the CAP theorem and the trade-offs it describes."),
        ("hard", "How would you go about debugging a memory leak in a long-running service?"),
    ],
    "hr": [
        ("easy", "Tell me about yourself."),
        ("easy", "Why do you want to work here?"),
        ("easy", "What do you know about our company?"),
        ("easy", "What are you looking for in your next role?"),
        ("easy", "How did you hear about this position?"),
        ("medium", "What are your greatest strengths and weaknesses?"),
        ("medium", "Where do you see yourself in five years?"),
        ("medium", "How do you handle stress or pressure at work?"),
        ("medium", "What motivates you in your work?"),
        ("medium", "How do you prioritize your tasks when everything feels urgent?"),
        ("hard", "Why should we hire you over other candidates?"),
        ("hard", "Describe a time you received difficult feedback. How did you respond?"),
        ("hard", "Describe a time you made a mistake at work. How did you handle it?"),
        ("hard", "How do you handle working with a manager you disagree with?"),
        ("hard", "What would your previous manager say is your biggest area for growth?"),
    ],
    "behavioral": [
        ("easy", "Describe a time you worked as part of a team."),
        ("easy", "Tell me about a goal you set and how you achieved it."),
        ("easy", "Describe a time you had to learn something new quickly."),
        ("easy", "Tell me about a time you helped a colleague solve a problem."),
        ("easy", "Describe a time you took initiative without being asked."),
        ("medium", "Tell me about a time you disagreed with a teammate and how you resolved it."),
        ("medium", "Describe a situation where you had to meet a tight deadline."),
        ("medium", "Tell me about a time you had to adapt to an unexpected change."),
        ("medium", "Describe a time you received critical feedback and how you responded."),
        ("medium", "Tell me about a time you had to balance multiple priorities at once."),
        ("hard", "Tell me about a time you failed. What did you learn?"),
        ("hard", "Describe a time you had to persuade someone who disagreed with you."),
        ("hard", "Describe a time you had to make a difficult decision with incomplete information."),
        ("hard", "Tell me about a time you took a risk that didn't pay off."),
        ("hard", "Describe a situation where you had to lead a team through a difficult challenge."),
    ],
}


def pick_questions(category: str, difficulty: str, count: int):
    """Returns (questions, insufficient).

    questions is a list of (question_id, text) tuples where every text is
    distinct - this never pads the result by cycling back through
    questions it has already picked. Preference order is: questions
    matching the requested difficulty first (in bank order), then the
    remaining questions in the same category (also in bank order), up to
    `count`.

    insufficient is True only when the category's entire bank has fewer
    than `count` distinct questions, in which case every available
    question is returned once (fewer than `count`) rather than ever
    repeating one to pad the list - callers should treat this as "the
    fixed question bank could not fully satisfy this request" and say so,
    not silently present a short, padded list as if it were full."""
    pool = DEMO_QUESTION_BANK[category]
    matching = [text for d, text in pool if d == difficulty]
    other = [text for d, text in pool if d != difficulty]
    ordered_unique = matching + other
    insufficient = count > len(ordered_unique)
    selected = ordered_unique[:count]
    return [(f"q{i + 1}", text) for i, text in enumerate(selected)], insufficient
