"""Message sorter: Jev judges each message, plain Python decides where it goes.

Run:  python sorter.py
Without a key in .env, it uses FAKE answers so you can try the flow for free.
"""

import json
import shutil
from pathlib import Path

import budget
from typesafe_sdk import (
    Choice,
    Noul,
    TypeSafeAPIError,
    TypeSafeAuthenticationError,
    TypeSafeClient,
    TypeSafePermissionDeniedError,
)

INBOX = Path("messages.json")
OUT = Path("sorted")

# Thresholds are starting points. Tune them once you see real results on your messages.
SPAM_THRESHOLD = 0.7      # be sure before hiding something in spam
URGENT_THRESHOLD = 0.6
MIN_CONFIDENCE = 0.4      # below this, the category is a guess -> send to review

CATEGORIES = {
    "work": "Job, colleagues, clients, meetings, code, deadlines",
    "personal": "Family, friends, social plans",
    "shopping": "Orders, deliveries, returns, store receipts",
    "finance": "Banks, bills, payments, account security from a financial institution",
    "newsletter": "Subscriptions, digests, marketing updates the reader signed up for",
    "other": "None of the above clearly fits",
}

# Three independent questions about the same message -> one request, answered in parallel.
QUESTIONS = {
    "spam": Noul(
        instructions="Is `message` spam, a scam, or phishing, rather than mail the "
        "recipient would want?"
    ),
    "urgent": Noul(
        instructions="Does `message` need the recipient to act today, for example a "
        "deadline today or a possible security problem?"
    ),
    "category": Choice(
        instructions="Which category best describes `message`?",
        criteria=CATEGORIES,
    ),
}


def judge_with_jev(client, message):
    budget.check()
    r = client.system_one(state={"message": message}, questions=QUESTIONS)
    budget.record(r.usage)
    category = r.answers["category"]
    return {
        "spam": r.answers["spam"].noul,
        "urgent": r.answers["urgent"].noul,
        "category": category.choice,
        "confidence": category.confidence,
    }


def judge_fake(message):
    """Keyword guesses that mimic Jev's answer shape. Only for trying the app."""
    text = (message["subject"] + " " + message["body"]).lower()
    has = lambda *words: any(w in text for w in words)
    category = (
        "work" if has("client", "meeting", "slides", "pull request") else
        "personal" if has("lunch", "dad", "mom") else
        "shopping" if has("order", "package", "shipped") else
        "finance" if has("bank", "bill", "payment") else
        "newsletter" if has("this week", "top stories") else
        "other"
    )
    return {
        "spam": 0.95 if has("winner", "free prize", "card details") else 0.05,
        "urgent": 0.85 if has("today", "immediately", "3pm") else 0.1,
        "category": category,
        "confidence": 0.3 if category == "other" else 0.8,
    }


def decide_folder(answer):
    """Our rules, in plain code. Jev never decides this directly."""
    if answer["spam"] >= SPAM_THRESHOLD:
        return "spam"
    if answer["confidence"] < MIN_CONFIDENCE:
        return "review"
    return answer["category"]


def main():
    messages = json.loads(INBOX.read_text(encoding="utf-8"))
    use_jev = budget.load_api_key()
    print("Using Jev\n" if use_jev else "No API key in .env: using FAKE answers\n")

    shutil.rmtree(OUT, ignore_errors=True)
    client = TypeSafeClient() if use_jev else None
    try:
        for i, message in enumerate(messages, 1):
            answer = judge_with_jev(client, message) if use_jev else judge_fake(message)
            folder = decide_folder(answer)
            urgent = answer["urgent"] >= URGENT_THRESHOLD

            dest = OUT / folder
            dest.mkdir(parents=True, exist_ok=True)
            name = f"{i:02d}{'_URGENT' if urgent else ''}.json"
            (dest / name).write_text(
                json.dumps({"message": message, "jev": answer}, indent=2), encoding="utf-8"
            )

            flag = "!!" if urgent else "  "
            print(
                f"{flag} {folder:<10} spam={answer['spam']:.0%}  urgent={answer['urgent']:.0%}  "
                f"conf={answer['confidence']:.0%}  {message['subject']}"
            )
    except (TypeSafeAuthenticationError, TypeSafePermissionDeniedError) as e:
        print(f"\nTypeSafe rejected the key or account (check key and credits): {e}")
    except budget.BudgetExceeded as e:
        print(f"\nBudget limit reached: {e}")
    except TypeSafeAPIError as e:
        print(f"\nTypeSafe API error: {e}")
    finally:
        if client:
            client.close()
            print("\n" + budget.summary())

    print(f"\nSorted files are in ./{OUT}/  (!! = urgent)")


if __name__ == "__main__":
    main()
