# Software Leads Weekly Index (SWLWi)

Welcome to the Software Leads Weekly Index (SWLWi) project! This project aims to transform the [Software Leads Weekly (SWLW) mailing list](https://softwareleadweekly.com/) into a comprehensive knowledge base for software engineering managers and leaders. By scraping, processing, and indexing the content of SWLW issues, we provide an efficient way to query and retrieve valuable information using a Retrieval Augmented Generation (RAG) model.

![SWLWi RAG Flow open in Flyde](flyde-rag.avif)

Build with [Flyde](https://flyde.dev) - Visual Programming tool for modern developers - and [PyFlyde](https://github.com/trustmaster/pyflyde) - Python library and runtime for Flyde with emphasis on Data-driven applications.

## Table of Contents

- [Concept](#concept)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Contributing](#contributing)
- [License](#license)

## Concept

The SWLWI project follows a multi-step process to build a knowledge base from the SWLW mailing list:

1. **Scraping Issues**: Fetches the list of all SWLW issues and their contents from the [SWLW Issues Page](https://softwareleadweekly.com/issues/). It parses the HTML page to get the list of issues and their URLs.
2. **Extracting Articles**: For each issue, it extracts all articles (title, summary, URL, reading time). It downloads each article, strips down the HTML to get just the content (as Markdown), and saves it locally.
3. **Indexing Articles**: The local database containing issues and articles is then scanned and turned into embeddings. These embeddings are used to create a RAG for querying the knowledge base.
4. **Taxonomy Extraction**: Extracts taxonomy labels from the articles and saves them as a separate table.
5. **Creating RAG**: Builds a RAG based on the taxonomy and the articles, and saves it in an SQLite vector database.
6. **Querying with Llama3**: Connects the Llama3 agent to the RAG, providing a standard querying API to ask questions and retrieve results from the local knowledge base.

## Features

- **Automated Scraping**: Automatically fetches and processes SWLW issues and articles.
- **Content Extraction**: Converts HTML content to clean Markdown format.
- **Efficient Indexing**: Uses embeddings to index articles for fast retrieval.
- **RAG Model**: Implements a Retrieval Augmented Generation model for querying the knowledge base.
- **Streamlit UI**: Provides a user-friendly interface to query the knowledge base.

## Installation

Make sure you have Python 3.10+ installed.

1. **Create and activate a virtual environment**:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

2. **Install the dependencies**:
    ```bash
    pip install .
    playwright install
    ```

## Usage

### Scraping SWLW Issues

To scrape SWLW issues and save the articles locally, run the following command:

```bash
pyflyde Scrape.flyde
```

### Indexing Articles

To index the articles and create embeddings, run the following command:

```bash
pyflyde Index.flyde
```

### Querying the Knowledge Base

To query the knowledge base using the Streamlit UI, run the following command:

```bash
streamlit run app.py
```

## Contributing

We welcome contributions to the SWLWi project! If you have any ideas, suggestions, or bug reports, please open an issue or submit a pull request.

## License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for more details.

## Credits and Fair Use Conditions

Software Leads Weekly is created by Oren Ellenbogen. All article copyrights belong to their original authors. This tool is created for educational purposes, use it with respect to the original copyrights.
