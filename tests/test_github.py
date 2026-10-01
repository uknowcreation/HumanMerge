import unittest

from pr_review_agent.github import aggregate_metadata


class MetadataGitHub:
    def languages(self, repository):
        return {
            "acme/web": {"TypeScript": 800, "CSS": 200},
            "acme/api": {"Python": 1200, "Shell": 10},
        }[repository]

    def labels(self, repository):
        return {
            "acme/web": ("front-end", "bug"),
            "acme/api": ("back-end", "bug"),
        }[repository]


class AggregateMetadataTests(unittest.TestCase):
    def test_languages_are_sorted_by_usage_and_labels_are_deduplicated(self):
        metadata = aggregate_metadata(MetadataGitHub(), ("acme/web", "acme/api"))

        self.assertEqual(metadata.languages, ("python", "typescript", "css", "shell"))
        self.assertEqual(metadata.labels, ("back-end", "bug", "front-end"))


if __name__ == "__main__":
    unittest.main()

