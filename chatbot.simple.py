"""
quick.py — minimal memory + thinking tutor bot on Groq.
No files, no database — memory lives in plain Python objects for the
session. Only external dependency is the groq package.

    pip install groq
    export GROQ_API_KEY=gsk_...
    python quick.py
"""

import os

from groq import Groq

client = Groq(api_key=os.environ["GROQ_API_KEY"])

BIG = "llama-3.3-70b-versatile"   # answers
SMALL = "llama-3.1-8b-instant"    # thinking + memory chores

SYSTEM = """You are Study Buddy, a patient tutor for a 2nd-year engineering student
(DSA, DBMS, OS, networks, digital logic, signals, thermo, engineering maths).
Intuition first, formalism second. For numericals show every step with units.
For code keep it short, commented, with complexity noted. Flag the traps that cost
marks in exams. If it looks like graded homework, teach the method on a parallel
example instead of handing over the answer. End heavy explanations with one quick
check-for-understanding question."""

# in-memory state — resets when the process exits
facts = []     # list[str]  durable things learned about the student
chat = []      # list[dict] recent turns, capped below


def ask(model, messages, temp=0.6, max_tokens=1200):
    resp = client.chat.completions.create(
        model=model, messages=messages, temperature=temp, max_tokens=max_tokens
    )
    return resp.choices[0].message.content.strip()


def norm(text):
    """Reduce a fact to its meaningful word set, for duplicate detection."""
    stop = {"student", "is", "the", "a", "an", "in", "of", "and", "to", "for", "with"}
    words = "".join(c if c.isalnum() else " " for c in text.lower()).split()
    return frozenset(w for w in words if w not in stop)


def learn(user, reply):
    """Ask the small model what's worth remembering long-term, skip near-dupes."""
    try:
        out = ask(SMALL, [
            {"role": "system", "content":
             "Extract durable facts about the student from this exchange, one per "
             "line, each starting with 'Student'. Keep branch, semester, weak "
             "topics, strengths, preferences, exam goals, ongoing projects. Skip "
             "anything transient — what they merely asked today doesn't count. "
             "If nothing durable came up, output exactly: none"},
            {"role": "user", "content": f"STUDENT: {user}\n\nTUTOR: {reply[:800]}"},
        ], temp=0, max_tokens=200)
    except Exception:
        return  # learning is a bonus, never worth crashing the chat over

    if out.strip().lower() == "none":
        return
    existing = {norm(f) for f in facts}
    for line in out.splitlines():
        line = line.strip("-• ").strip()
        if line and norm(line) not in existing and norm(line):
            facts.append(line)
            existing.add(norm(line))
    del facts[:-60]  # keep only the most recent 60


def main():
    print("🧠 Study Buddy  (/memory · /forget · /new · /quit)\n")

    while True:
        user = input("you › ").strip()
        if not user:
            continue
        if user == "/quit":
            break
        if user == "/memory":
            print("\n".join(f"  {i}. {f}" for i, f in enumerate(facts, 1)) or "  (empty)", "\n")
            continue
        if user == "/forget":
            facts.clear()
            print("  memory cleared\n")
            continue
        if user == "/new":
            chat.clear()
            print("  chat history cleared, facts kept\n")
            continue

        # 1. THINK — private planning pass on the cheap model
        try:
            plan = ask(SMALL, [
                {"role": "system", "content":
                 "You are a tutor's private scratchpad. Plan the answer: what is "
                 "really being asked, what concept applies, what order to explain "
                 "in, what trap to warn about. Under 120 words. Never shown to the "
                 "student."},
                {"role": "user", "content": user},
            ], temp=0.3, max_tokens=300)
            print(f"\n\033[2m💭 {plan}\033[0m\n")
        except Exception as e:
            plan = ""
            print(f"\n\033[2m(planning skipped: {e})\033[0m\n")

        # 2. ANSWER — memory + last 10 turns + the plan
        system = SYSTEM
        if facts:
            system += "\n\nYou remember about this student:\n" + "\n".join("- " + f for f in facts)

        messages = [{"role": "system", "content": system}] + chat[-10:] + [
            {"role": "user", "content":
             f"{user}\n\n[Private plan, follow it silently:\n{plan}]" if plan else user}
        ]

        print("buddy › ", end="", flush=True)
        reply = ""
        try:
            for ev in client.chat.completions.create(
                model=BIG, messages=messages, temperature=0.6, max_tokens=1800, stream=True
            ):
                tok = ev.choices[0].delta.content
                if tok:
                    reply += tok
                    print(tok, end="", flush=True)
        except Exception as e:
            print(f"\n[error: {e}]")
            continue
        print("\n")

        # 3. REMEMBER — keep last 20 messages, extract durable facts
        chat.append({"role": "user", "content": user})
        chat.append({"role": "assistant", "content": reply})
        del chat[:-20]
        learn(user, reply)


if __name__ == "__main__":
    main()
