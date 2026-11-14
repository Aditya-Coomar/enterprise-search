import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from rank import rank


class PassageRetrievalTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.metadata = {"model_id": "test", "revision": "1", "dimensions": 2}
        self.job = {
            "root": str(self.root),
            "prefix": "doc/",
            "query": "What is the waiting period for cataract surgery?",
            "mode": "text",
            "dense": {"vector": [1, 0], "metadata": self.metadata},
            "pages": [],
            "includeEvidence": True,
        }

    def artifact(self, name, value):
        key = "doc/" + name
        data = json.dumps(value).encode()
        destination = self.root / key
        destination.parent.mkdir(exist_ok=True)
        destination.write_bytes(data)
        return {"key": key, "sha256": hashlib.sha256(data).hexdigest()}

    def page(self, number, passages, vectors):
        chunks = [
            {"chunk_id": str(index), "text": text, "section_title": section}
            for index, (text, section) in enumerate(passages)
        ]
        artifacts = {
            "extraction": self.artifact(f"{number}-text", {
                "text": "\n".join(text for text, _ in passages),
                "page_number": number,
                "elements": [],
            }),
            "chunks": self.artifact(f"{number}-chunks", {"chunks": chunks}),
            "text_embeddings": self.artifact(f"{number}-vectors", [
                {"chunk_id": str(index), "vector": vector, "metadata": self.metadata}
                for index, vector in enumerate(vectors)
            ]),
        }
        self.job["pages"].append({"page": number, "artifacts": artifacts})

    def test_reranks_focused_evidence_above_page_wide_keyword_matches(self):
        for number in range(1, 6):
            self.page(number, [
                ("Waiting period inquiries are handled by member services.", "Contacts"),
                ("Cataract surgery providers are listed in the directory.", "Providers"),
            ], [[0.4, 0.9165], [0.4, 0.9165]])
        self.page(6, [
            ("Benefits begin after 24 months of continuous coverage.", "Cataract surgery waiting period"),
            ("The period is waived for accidental injury.", "Cataract surgery waiting period"),
            ("An unrelated benefit is described here.", "Other benefits"),
        ], [[1, 0], [0.2, 0.98], [0, 1]])

        output = rank(self.job)
        self.assertEqual(output["results"][0]["page"], 6)
        self.assertEqual(output["evidence"][0]["page"], 6)
        excerpts = " ".join(output["evidence"][0]["passages"])
        self.assertIn("24 months", excerpts)
        self.assertIn("waived for accidental injury", excerpts)
        self.assertNotIn("unrelated benefit", excerpts)

    def test_lexical_retrieval_works_without_query_embeddings(self):
        self.job["dense"] = None
        self.page(1, [("Cataract surgery has a 24-month waiting period.", None)], [])
        self.assertEqual(rank(self.job)["results"][0]["signals"], ["Keyword"])

    def test_unrelated_document_supplies_no_evidence(self):
        self.page(1, [("Dental cleaning is covered.", None)], [[0, 1]])
        self.assertEqual(rank(self.job), {"results": [], "evidence": []})
