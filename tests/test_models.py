import json
import unittest

from pr_review_agent.models import Finding, ReviewResult, Severity


class ReviewResultTests(unittest.TestCase):
    def test_analysis_cannot_authorize_publication(self) -> None:
        review = ReviewResult(
            repository="example/project",
            pull_request=42,
            head_sha="abc123",
            reviewer="frontend",
            findings=(),
            publish_allowed=True,
        )
        with self.assertRaisesRegex(ValueError, "cannot authorize publication"):
            review.validate()

    def test_serializes_valid_finding(self) -> None:
        finding = Finding(
            severity=Severity.HIGH,
            title="Focus state disappears",
            explanation="Keyboard users cannot locate the active control.",
            proposed_comment="Could we keep a visible :focus-visible state here?",
            path="src/Button.tsx",
            line=18,
            confidence=0.94,
        )
        review = ReviewResult(
            repository="example/project",
            pull_request=42,
            head_sha="abc123",
            reviewer="frontend",
            findings=(finding,),
        )
        payload = json.loads(review.to_json())
        self.assertEqual(payload["findings"][0]["severity"], "high")
        self.assertFalse(payload["publish_allowed"])


if __name__ == "__main__":
    unittest.main()

