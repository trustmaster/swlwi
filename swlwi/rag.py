"""Retrieval Augmented Generation (RAG) model."""

import os
import sqlite3

import ollama
from flyde.io import Input, InputMode, Output
from flyde.node import Component, logger
from langchain_community.vectorstores import SQLiteVec
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI
from langchain_text_splitters import MarkdownTextSplitter


class ListArticles(Component):
    """Lists all articles in the index."""

    inputs = {"path": Input(description="Path to the index", type=str, mode=InputMode.STICKY, value="./index")}

    outputs = {"article_path": Output(description="Stream of paths to articles", type=str)}

    def process(self, path: str) -> None:
        for issue in os.listdir(path):
            # Skip folders that don't start with 'issue-'
            if not issue.startswith("issue-"):
                continue
            issue_path = os.path.join(path, issue)
            for article in os.listdir(issue_path):
                # Skip files that don't end with '.md'
                if not article.endswith(".md"):
                    continue
                article_path = os.path.join(issue_path, article)
                self.send("article_path", article_path)
        # Send EOF when finished listing
        logger.info("Finished listing articles")
        self.stop()


class DocumentLoader(Component):
    """Loads Markdown from file as a Langchain Document."""

    inputs = {"path": Input(description="Path to the markdown file", type=str)}

    outputs = {"document": Output(description="Langchain Document", type=Document)}

    def process(self, path: str) -> dict[str, Document]:
        logger.info(f"Loading document from {path}")
        with open(path, "r") as f:
            text = f.read()

        # Parse header
        header = text.split("\n---\n")[0]
        lines = header.split("\n")
        title = lines[0].strip("# \t\r\n")
        lines = lines[1:]
        source_url = ""
        reading_time = ""
        summary_lines = []

        for line in lines:
            if line.startswith("Source:"):
                source_url = line.split("(")[-1].strip(")")
            elif line.startswith("Reading time:"):
                reading_time = line.split(":")[-1].strip()
            else:
                summary_lines.append(line)

        summary = "\n".join(summary_lines).strip()

        doc = Document(
            page_content=text,
            metadata={
                "path": path,
                "title": title,
                "source_url": source_url,
                "reading_time": reading_time,
                "summary": summary,
            },
        )
        logger.info(f"Loaded document: {title} from {path}")
        return {"document": doc}


class DocumentSplitter(Component):
    """Splits markdown documents into chunks."""

    inputs = {
        "document": Input(description="Document to split", type=Document),
        "chunk_size": Input(description="Size of each chunk", type=int, mode=InputMode.STICKY, value=2000),
    }

    outputs = {"documents": Output(description="Chunks of text")}

    def process(self, document: Document, chunk_size: int) -> dict[str, list[Document]]:
        splitter = MarkdownTextSplitter(chunk_size=chunk_size, chunk_overlap=50)
        texts = [document.page_content]
        metadatas = [document.metadata]
        documents = splitter.create_documents(texts, metadatas)
        logger.info(f"Split document {document.metadata['path']} into {len(documents)} chunks")
        return {"documents": documents}


class VectorStore(Component):
    """Stores documents as vectors in a vector store."""

    inputs = {
        "documents": Input(description="Documents to store"),
        "path": Input(description="Path to the vector store", type=str, mode=InputMode.STICKY, value="./index/vectors"),
    }

    def _init(self, path: str):
        if not hasattr(self, "_embeddings"):
            logger.info("Loading embeddings")
            self._embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        if not hasattr(self, "_vector_store"):
            logger.info("Creating vector store")
            # Create path if not exists
            os.makedirs(path, exist_ok=True)
            self._vector_store = SQLiteVec(
                table="swlwi_embeddings", connection=None, db_file=f"{path}/db.sqlite3", embedding=self._embeddings
            )

    def process(self, documents: list, path: str):
        logger.info(f"VectorStore Processing {len(documents)} documents")
        self._init(path)
        logger.info(f"Adding {len(documents)} documents from {documents[0].metadata['path']} to the vector store")
        try:
            self._vector_store.add_documents(documents)
        except sqlite3.OperationalError as e:
            if "UNIQUE constraint failed" in str(e):
                logger.info("Some documents already exist in the vector store, skipping duplicates")
            else:
                # Re-raise if it's a different error
                raise


class Retriever(Component):
    """Retrieves context from a vector store."""

    inputs = {
        "query": Input(description="Query text", type=str),
        "path": Input(description="Path to the vector store", type=str, mode=InputMode.STICKY, value="./index/vectors"),
    }

    outputs = {"context": Output(description="Context retrieved from the vector store", type=str)}

    def _init(self, path: str):
        if not hasattr(self, "_embeddings"):
            self._embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        if not hasattr(self, "_vector_store"):
            logger.info(f"Opening vector store with path {path}/db.sqlite")
            self._vector_store = SQLiteVec(
                table="swlwi_embeddings", connection=None, db_file=f"{path}/db.sqlite3", embedding=self._embeddings
            )
        if not hasattr(self, "_retriever"):
            self._retriever = self._vector_store.as_retriever()

    def process(self, query: str, path: str) -> dict[str, str]:
        self._init(path)

        docs = self._retriever.invoke(query)

        logger.info(f"Retrieved {len(docs)} documents from the vector store for query '{query}'")

        if not docs:
            return {"context": ""}

        context = "\n\n".join([doc.page_content for doc in docs])
        return {"context": context}


class OllamaChat(Component):
    """Chat with the Ollama model."""

    inputs = {
        "query": Input(description="Query text", type=str),
        "context": Input(description="Context text", type=str),
    }

    outputs = {"response": Output(description="Response from the Ollama model", type=str)}

    def process(self, query: str, context: str) -> dict[str, str]:
        logger.info(f"Loaded context:\n\n {context}\n\n")

        # System prompt tells the agent about their role and sets ground rules
        system_prompt = "Given a question and context by user, use the context and your prior knowledge to answer the user's question."

        # Our user prompt
        prompt = f"Question: {query}\n\nContext: {context}"

        # Invoke the model
        response = ollama.chat(
            model="llama3.2",  # Replace this with other model string if needed, e.g. "phi4"
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
        )
        return {"response": response["message"]["content"]}


class OpenAIChat(Component):
    """Chat with the OpenAI model."""

    inputs = {
        "query": Input(description="Query text", type=str),
        "context": Input(description="Context text", type=str),
    }

    outputs = {"response": Output(description="Response from the OpenAI model", type=str)}

    def _init(self):
        if not hasattr(self, "_llm"):
            self._llm = ChatOpenAI(model="gpt-4o")

    def process(self, query: str, context: str) -> dict[str, str]:
        logger.info(f"Loaded context:\n\n {context}\n\n")

        # Load the model if needed
        self._init()

        # Construct the prompts
        system_prompt = "Given a question and context by user, use the context and your prior knowledge to answer the user's question."
        prompt = f"Question: {query}\n\nContext: {context}"

        # Invoke the model
        response = self._llm.invoke([("system", system_prompt), ("human", prompt)])

        return {"response": response.content}  # type: ignore
