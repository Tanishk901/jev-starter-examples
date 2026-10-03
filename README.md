# Jev Starter Examples

Two small Python apps built on [Jev](https://docs.typesafe.ai), TypeSafe's System One model.
Jev returns typed judgments (probabilities) instead of text, and plain Python decides what to do with them.

| Project | What Jev judges | What the code does |
|---|---|---|
| [`sorter.py`](sorter.py): message sorter | Is it spam? (Noul) · Is it urgent? (Noul) · Which category? (Choice) | Files each message into `sorted/<category>/`, marks urgent ones |
| [`router.py`](router.py): support ticket router | Which team? (Choice) · How urgent? (Score 0–3) · Security problem? (Noul) | Writes `queues/<team>.json` sorted by priority, sends unsure cases to `human_review` |

Both scripts run **without an API key** using fake keyword-based answers, so you can try them for free.

## Quick start

```bash
pip install typesafe-sdk
python sorter.py      # fake answers
python router.py      # fake answers
```

To use real Jev, get a key at [console.typesafe.ai](https://console.typesafe.ai/), then:

```bash
cp .env.example .env  # Windows: copy .env.example .env
# edit .env and paste your key after TYPESAFE_API_KEY=
python sorter.py      # first line should say "Using Jev"
```

## Example output (real Jev)

```
!! work       spam=5%  urgent=98%  conf=100%  Client deck needed before 3pm
   spam       spam=99%  urgent=50%  conf=95%  CONGRATULATIONS you won an iPhone!!!
   personal   spam=2%  urgent=17%  conf=100%  Sunday lunch
!! finance    spam=50%  urgent=91%  conf=100%  Unusual sign-in to your account

Total Jev spend so far: $0.000176 of $5.00 (8 requests, 4,198 input tokens)
```

Note the bank alert at `spam=50%`: real phishing looks exactly like that, so Jev is honestly unsure.
The 70% spam threshold keeps it in `finance/`. Thresholds live at the top of each script.

## How it works

```
input JSON ──► Jev answers questions ──► your rules in Python ──► output folders/queues
               (one request per item,     (thresholds, routing,
                questions run in parallel)  human review)
```

- **Jev never makes the decision.** It returns numbers like `team: billing 81%` or `urgency: 2.7 / 3`;
  `decide_folder()` and `route()` turn them into actions.
- **Uncertainty is used, not hidden.** Low confidence or an `unclear` answer sends a ticket to a person,
  with the reason attached.
- **Security is asked separately**, so a possible account takeover can't be averaged away inside the urgency score.

## Cost and spending cap

Jev costs $0.042 per million input tokens (output is free); one run of either script is roughly $0.0002.
[`budget.py`](budget.py) records every call in `spend.json` and refuses any call that could push the total past
`LIMIT_USD` (default $5). It only counts calls made by these scripts.

## Files

```
sorter.py, messages.json   message sorter and sample messages
router.py, tickets.json    ticket router and sample tickets
budget.py                  loads the key from .env, tracks spend, enforces the cap
.env.example               copy to .env and add your key (.env is git-ignored)
```

## License

[MIT](LICENSE)
