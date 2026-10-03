"""Support ticket router: Jev picks the team and rates urgency, code routes the ticket.

Run:  python router.py
Without a key in .env, it uses FAKE answers so you can try the flow for free.
"""

import json
import shutil
from pathlib import Path

import budget
from typesafe_sdk import (
    Choice,
    Noul,
    Score,
    TypeSafeAPIError,
    TypeSafeAuthenticationError,
    TypeSafeClient,
    TypeSafePermissionDeniedError,
)

TICKETS = Path("tickets.json")
OUT = Path("queues")

# Thresholds are starting points. Tune them on real tickets once you have a key.
MIN_TEAM_CONFIDENCE = 0.5     # below this, the team pick is a guess -> human
MIN_URGENCY_CONFIDENCE = 0.3  # urgency often splits between neighbouring levels; only flag a real spread
SECURITY_THRESHOLD = 0.5      # a possible security problem always goes to a human, as P1
MIN_DETAIL = 0.5              # below this, someone must ask the customer what is wrong first

TEAMS = {
    "billing": "Charges, refunds, invoices, plans, seat counts the customer pays for",
    "technical": "Bugs, errors, outages, features not working as expected",
    "account": "Login, passwords, profile and account settings",
    "shipping": "Physical deliveries, tracking, lost or late packages",
    "feedback": "Praise, suggestions or comments that need no fix",
    "unclear": "The ticket does not say enough to know which team should handle it",
}

# Levels go from least (0) to most (3) urgent. Each describes a situation, not a degree.
URGENCY_LEVELS = [
    "No problem to fix: a question, compliment or suggestion",
    "Minor problem with an easy workaround, or a how-to question",
    "Customer is blocked from something they need, or money is wrong, but it is limited to them",
    "Many users cannot work, money is being lost right now, or an account may be compromised",
]

# Four independent questions about the same ticket -> one request, answered in parallel.
QUESTIONS = {
    "team": Choice(
        instructions="Which support team should handle `ticket`?",
        criteria=TEAMS,
    ),
    "urgency": Score(
        instructions="How urgent is `ticket` for the customer?",
        criteria=URGENCY_LEVELS,
    ),
    # Asked separately so a security risk can't be averaged away inside the urgency score.
    "security": Noul(
        instructions="Does `ticket` describe a possible security problem, such as an "
        "account takeover, unauthorized password change, or leaked data?"
    ),
    # A vague ticket can still look like an obvious team ("not working" -> technical),
    # so whether it is actionable is its own question.
    "has_detail": Noul(
        instructions="Could a support agent start working on `ticket` without first asking "
        "the customer what is wrong? Answer yes if the problem is described, or if the "
        "ticket is a clear question or a compliment that needs no fix."
    ),
}


def judge_with_jev(client, ticket):
    budget.check()
    r = client.system_one(state={"ticket": ticket}, questions=QUESTIONS)
    budget.record(r.usage)
    team, urgency = r.answers["team"], r.answers["urgency"]
    return {
        "team": team.choice,
        "team_confidence": team.confidence,
        "urgency": urgency.score,
        "urgency_confidence": urgency.confidence,
        "security": r.answers["security"].noul,
        "has_detail": r.answers["has_detail"].noul,
    }


def judge_fake(ticket):
    """Keyword guesses that mimic Jev's answer shape. Only for trying the app."""
    text = ticket["text"].lower()
    has = lambda *words: any(w in text for w in words)
    team = (
        "account" if has("password", "log in", "profile") else
        "billing" if has("charged", "refund", "billed") else
        "technical" if has("error", "button", "500") else
        "shipping" if has("package", "tracking") else
        "feedback" if has("love", "great work") else
        "unclear"
    )
    urgency = (
        3.0 if has("nobody can work", "didn't do it") else
        2.0 if has("charged twice", "billed", "last week") else
        1.0 if has("how do i", "not a big deal") else
        0.0 if team == "feedback" else 1.5
    )
    return {
        "team": team,
        "team_confidence": 0.3 if team == "unclear" else 0.85,
        "urgency": urgency,
        "urgency_confidence": 0.7,
        "security": 0.9 if has("didn't do it") else 0.02,
        "has_detail": 0.1 if len(text) < 40 else 0.95,
    }


def priority(urgency):
    """Turn the 0-3 urgency position into P1 (most urgent) to P4."""
    if urgency >= 2.5:
        return "P1"
    if urgency >= 1.5:
        return "P2"
    if urgency >= 0.5:
        return "P3"
    return "P4"


def route(answer):
    """Our rules, in plain code. Returns (queue, priority, reasons for human review)."""
    reasons = []
    if answer["security"] >= SECURITY_THRESHOLD:
        reasons.append("possible security problem")
    if answer["team"] == "unclear":
        reasons.append("not enough detail to pick a team")
    elif answer["team_confidence"] < MIN_TEAM_CONFIDENCE:
        reasons.append(f"unsure of team ({answer['team_confidence']:.0%} confident)")
    if answer["has_detail"] < MIN_DETAIL:
        reasons.append("too vague: ask customer for details")
    if answer["urgency_confidence"] < MIN_URGENCY_CONFIDENCE:
        reasons.append(f"unsure of urgency ({answer['urgency_confidence']:.0%} confident)")

    prio = "P1" if answer["security"] >= SECURITY_THRESHOLD else priority(answer["urgency"])
    queue = "human_review" if reasons else answer["team"]
    return queue, prio, reasons


def main():
    tickets = json.loads(TICKETS.read_text(encoding="utf-8"))
    use_jev = budget.load_api_key()
    print("Using Jev\n" if use_jev else "No API key in .env: using FAKE answers\n")

    queues = {}
    client = TypeSafeClient() if use_jev else None
    try:
        for ticket in tickets:
            answer = judge_with_jev(client, ticket) if use_jev else judge_fake(ticket)
            queue, prio, reasons = route(answer)
            queues.setdefault(queue, []).append(
                {"priority": prio, "ticket": ticket, "jev": answer, "review_reasons": reasons}
            )
            note = f"  <- {'; '.join(reasons)}" if reasons else ""
            text = ticket["text"] if len(ticket["text"]) <= 50 else ticket["text"][:47] + "..."
            print(f"{prio}  {queue:<13} {ticket['id']}  {text:<50}{note}")
    except (TypeSafeAuthenticationError, TypeSafePermissionDeniedError) as e:
        print(f"\nTypeSafe rejected the key or account (check key and credits): {e}")
        return
    except budget.BudgetExceeded as e:
        print(f"\nBudget limit reached: {e}")
        return
    except TypeSafeAPIError as e:
        print(f"\nTypeSafe API error: {e}")
        return
    finally:
        if client:
            client.close()
            print("\n" + budget.summary())

    # One file per queue, most urgent first.
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir()
    for queue, items in queues.items():
        items.sort(key=lambda item: item["priority"])
        (OUT / f"{queue}.json").write_text(json.dumps(items, indent=2), encoding="utf-8")

    print(f"\nQueues written to ./{OUT}/: " + ", ".join(f"{q} ({len(i)})" for q, i in queues.items()))


if __name__ == "__main__":
    main()
