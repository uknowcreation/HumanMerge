import unittest

from pr_review_agent.policy import PullRequestMetadata, ReviewPolicy


class ReviewPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = ReviewPolicy(current_user="nicolas", required_label="front-end")

    def test_accepts_matching_foreign_pull_request(self) -> None:
        pull_request = PullRequestMetadata(
            author="alice",
            labels=frozenset({"front-end"}),
            is_draft=False,
            state="open",
            head_sha="abc123",
        )
        self.assertTrue(self.policy.is_eligible(pull_request))

    def test_rejects_own_pull_request(self) -> None:
        pull_request = PullRequestMetadata(
            author="Nicolas",
            labels=frozenset({"front-end"}),
            is_draft=False,
            state="open",
            head_sha="abc123",
        )
        self.assertEqual(
            self.policy.rejection_reason(pull_request),
            "pull request belongs to the current user",
        )

    def test_rejects_draft_or_missing_label(self) -> None:
        draft = PullRequestMetadata(
            author="alice",
            labels=frozenset({"front-end"}),
            is_draft=True,
            state="open",
            head_sha="abc123",
        )
        missing_label = PullRequestMetadata(
            author="alice",
            labels=frozenset(),
            is_draft=False,
            state="open",
            head_sha="abc123",
        )
        self.assertFalse(self.policy.is_eligible(draft))
        self.assertFalse(self.policy.is_eligible(missing_label))


if __name__ == "__main__":
    unittest.main()

