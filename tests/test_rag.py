import os
import unittest
from unittest.mock import patch, mock_open, MagicMock
from langchain_core.documents import Document
from swlwi.rag import ListArticles, DocumentLoader, DocumentSplitter


class TestListArticles(unittest.TestCase):
    @patch("os.listdir")
    def test_process(self, mock_listdir):
        # Mock the directory structure
        mock_listdir.side_effect = [
            ["issue-1", "issue-2"],  # First call returns issues
            ["article-1.md", "article-2.md"],  # Second call returns articles for issue-1
            ["article-1.md", "article-2.md"],  # Third call returns articles for issue-2
        ]

        # Create an instance of ListArticles
        list_articles = ListArticles(id="List Articles")

        # Mock the send method to capture the output
        list_articles.send = MagicMock()

        # Call the process method
        list_articles.process("./index")

        # Check that the send method was called four times (two articles per issue)
        self.assertEqual(4, list_articles.send.call_count)

        # Check the arguments of the first call
        first_call_args = list_articles.send.call_args_list[0][0]
        self.assertEqual("article_path", first_call_args[0])
        self.assertEqual(os.path.join("./index", "issue-1", "article-1.md"), first_call_args[1])

        # Check the arguments of the second call
        second_call_args = list_articles.send.call_args_list[1][0]
        self.assertEqual("article_path", second_call_args[0])
        self.assertEqual(os.path.join("./index", "issue-1", "article-2.md"), second_call_args[1])

        # Check the arguments of the third call
        third_call_args = list_articles.send.call_args_list[2][0]
        self.assertEqual("article_path", third_call_args[0])
        self.assertEqual(os.path.join("./index", "issue-2", "article-1.md"), third_call_args[1])

        # Check the arguments of the fourth call
        fourth_call_args = list_articles.send.call_args_list[3][0]
        self.assertEqual("article_path", fourth_call_args[0])
        self.assertEqual(os.path.join("./index", "issue-2", "article-2.md"), fourth_call_args[1])

        # # Check the arguments of the fifth call
        # fifth_call_args = list_articles.send.call_args_list[4][0]
        # self.assertEqual("article_path", fifth_call_args[0])
        # self.assertEqual(EOF, fifth_call_args[1])


class TestDocumentLoader(unittest.TestCase):
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="""# Some Article

Source: [http://example.com](http://example.com)
Reading time: 3 minutes

Article summary

---

Some text
Some more text
""",
    )
    def test_process(self, mock_open):
        # Create an instance of DocumentLoader
        document_loader = DocumentLoader(id="Document Loader")

        # Mock the send method to capture the output
        document_loader.send = MagicMock()

        # Call the process method
        result = document_loader.process("/fake/path/article.md")

        # Check that the file was opened with the correct arguments
        mock_open.assert_called_once_with("/fake/path/article.md", "r")

        # Check the document content
        document = result.get("document")
        if document is None:
            self.fail("No document found in the result")

        self.assertIsInstance(document, Document)
        self.assertEqual(
            document.page_content,
            """# Some Article

Source: [http://example.com](http://example.com)
Reading time: 3 minutes

Article summary

---

Some text
Some more text
""",
        )
        self.assertEqual(document.metadata["path"], "/fake/path/article.md")
        self.assertEqual(document.metadata["title"], "Some Article")
        self.assertEqual(document.metadata["source_url"], "http://example.com")
        self.assertEqual(document.metadata["reading_time"], "3 minutes")
        self.assertEqual(document.metadata["summary"], "Article summary")


class TestDocumentSplitter(unittest.TestCase):
    def test_process(self):
        # Example document content
        example_content = """# Some Article about Chunks

Some text here to split into chunks. Chunks are useful for processing large documents.

Some more text to ensure we have enough content to split into chunks. We love chunks. Chunks are great. Chunky bacon is even better.

Even more text to ensure we have enough content to split into chunks. Chunks are all here. This is the last sentence.
"""
        example_metadata = {
            "path": "/fake/path/article.md",
            "title": "Some Article",
            "source_url": "http://example.com",
            "reading_time": "3 minutes",
            "summary": "Article summary",
        }

        # Create a mock Document object
        mock_document = Document(page_content=example_content, metadata=example_metadata)
        chunk_size = 200

        # Create an instance of DocumentSplitter
        document_splitter = DocumentSplitter(id="Document Splitter")

        # Call the process method with the mock Document
        result = document_splitter.process(mock_document, chunk_size)

        # Check the documents content
        documents = result.get("documents")
        if documents is None:
            self.fail("No documents found in the result")

        self.assertIsInstance(documents, list)
        self.assertGreater(len(documents), 1)  # Ensure that the document was split into multiple chunks

        for doc in documents:
            self.assertIsInstance(doc, Document)
            self.assertIn("Chunk", doc.page_content)  # Ensure that the content is part of the split documents
            self.assertEqual(doc.metadata["path"], example_metadata["path"])
            self.assertEqual(doc.metadata["title"], example_metadata["title"])
            self.assertEqual(doc.metadata["source_url"], example_metadata["source_url"])
            self.assertEqual(doc.metadata["reading_time"], example_metadata["reading_time"])
            self.assertEqual(doc.metadata["summary"], example_metadata["summary"])


if __name__ == "__main__":
    unittest.main()
