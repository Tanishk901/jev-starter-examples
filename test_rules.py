"""Tests for the Python rules that turn Jev's answers into actions. No API key needed.

Run:  python -m unittest -v
"""

import unittest

from router import route
from sorter import decide_folder


def ticket_answer(**overrides):
    """A clear, routine ticket; each test changes only what it checks."""
    answer = {
        "team": "billing",
        "team_confidence": 0.95,
        "urgency": 2.0,
        "urgency_confidence": 0.9,
        "security": 0.02,
        "has_detail": 0.96,
    }
    answer.update(overrides)
    return answer


def message_answer(**overrides):
    answer = {"spam": 0.05, "urgent": 0.1, "category": "work", "confidence": 0.95}
    answer.update(overrides)
    return answer


class RouterRules(unittest.TestCase):
    def test_clear_ticket_goes_to_its_team(self):
        self.assertEqual(route(ticket_answer()), ("billing", "P2", []))

    def test_urgency_maps_to_priority(self):
        for urgency, expected in [(3.0, "P1"), (2.5, "P1"), (1.6, "P2"), (1.0, "P3"), (0.2, "P4")]:
            self.assertEqual(route(ticket_answer(urgency=urgency))[1], expected, urgency)

    def test_security_problem_goes_to_human_as_p1(self):
        queue, prio, reasons = route(ticket_answer(security=0.97, urgency=0.5))
        self.assertEqual((queue, prio), ("human_review", "P1"))
        self.assertIn("possible security problem", reasons)

    def test_vague_ticket_goes_to_human_even_with_confident_team(self):
        # Real Jev: "It's not working again. Fix it." -> technical 97%, has_detail 6%
        queue, _, reasons = route(ticket_answer(team="technical", team_confidence=0.97, has_detail=0.06))
        self.assertEqual(queue, "human_review")
        self.assertIn("too vague: ask customer for details", reasons)

    def test_unclear_or_unsure_team_goes_to_human(self):
        self.assertEqual(route(ticket_answer(team="unclear"))[0], "human_review")
        self.assertEqual(route(ticket_answer(team_confidence=0.4))[0], "human_review")


class SorterRules(unittest.TestCase):
    def test_normal_message_goes_to_its_category(self):
        self.assertEqual(decide_folder(message_answer()), ("work", ""))

    def test_clear_spam(self):
        self.assertEqual(decide_folder(message_answer(spam=0.99))[0], "spam")

    def test_possible_phishing_goes_to_review(self):
        # Real Jev: bank "Unusual sign-in" alert scored 50% spam
        folder, reason = decide_folder(message_answer(spam=0.5, category="finance"))
        self.assertEqual(folder, "review")
        self.assertIn("phishing", reason)

    def test_unsure_category_goes_to_review(self):
        self.assertEqual(decide_folder(message_answer(confidence=0.3))[0], "review")


if __name__ == "__main__":
    unittest.main()
