import { CodeNode } from "@flyde/core";

export const ListArticles: CodeNode = {
  id: "ListArticles",
  description: "Lists all articles in the index.",
  inputs: {
    path: { description: "Path to the index" }
  },
  outputs: {
    article_path: { description: "Stream of paths to articles" }
  },
  run: () => { return; },
};

export const DocumentLoader: CodeNode = {
  id: "DocumentLoader",
  description: "Loads Markdown from file as a Langchain Document.",
  inputs: {
    path: { description: "Path to the markdown file" }
  },
  outputs: {
    document: { description: "Langchain Document" }
  },
  run: () => { return; },
};

export const DocumentSplitter: CodeNode = {
  id: "DocumentSplitter",
  description: "Splits markdown documents into chunks.",
  inputs: {
    document: { description: "Document to split" },
    chunk_size: { description: "Size of each chunk" }
  },
  outputs: {
    documents: { description: "Chunks of text" }
  },
  run: () => { return; },
};

export const VectorStore: CodeNode = {
  id: "VectorStore",
  description: "Stores documents as vectors in a vector store.",
  inputs: {
    documents: { description: "Documents to store" },
    path: { description: "Path to the vector store" }
  },
  outputs: {  },
  run: () => { return; },
};

export const Retriever: CodeNode = {
  id: "Retriever",
  description: "Retrieves context from a vector store.",
  inputs: {
    query: { description: "Query text" },
    path: { description: "Path to the vector store" }
  },
  outputs: {
    context: { description: "Context retrieved from the vector store" }
  },
  run: () => { return; },
};

export const OllamaChat: CodeNode = {
  id: "OllamaChat",
  description: "Chat with the Ollama model.",
  inputs: {
    query: { description: "Query text" },
    context: { description: "Context text" }
  },
  outputs: {
    response: { description: "Response from the Ollama model" }
  },
  run: () => { return; },
};

export const OpenAIChat: CodeNode = {
  id: "OpenAIChat",
  description: "Chat with the OpenAI model.",
  inputs: {
    query: { description: "Query text" },
    context: { description: "Context text" }
  },
  outputs: {
    response: { description: "Response from the OpenAI model" }
  },
  run: () => { return; },
};

