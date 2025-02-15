import { CodeNode } from "@flyde/core";

export const ListIssues: CodeNode = {
  id: "ListIssues",
  description: "Fetches the index by the URL, parses it and returns a stream of issues and their URLs.",
  inputs: {
    url: { description: "URL of the index page" },
    limit: { description: "Limit the number of issues to fetch" }
  },
  outputs: {
    issue: { description: "List of issues" }
  },
  run: () => { return; },
};

export const SkipExistingIssues: CodeNode = {
  id: "SkipExistingIssues",
  description: "Checks if an issue already exists in the database and skips it if it does.",
  inputs: {
    issue: { description: "Issue" },
    path: { description: "Path to the database" },
    force_all: { description: "Force processing all issues" }
  },
  outputs: {
    issue: { description: "Issue" }
  },
  run: () => { return; },
};

export const ExtractArticles: CodeNode = {
  id: "ExtractArticles",
  description: "Extracts articles from the issue page.",
  inputs: {
    issue: { description: "Issue" }
  },
  outputs: {
    article: { description: "Article" }
  },
  run: () => { return; },
};

export const FetchArticle: CodeNode = {
  id: "FetchArticle",
  description: "Fetches the article HTML from the internet.",
  inputs: {
    article: { description: "Article" }
  },
  outputs: {
    complete: { description: "Article with HTML content" },
    needs_javascript: { description: "Article that needs JavaScript to fetch" }
  },
  run: () => { return; },
};

export const FetchArticleWithJavaScript: CodeNode = {
  id: "FetchArticleWithJavaScript",
  description: "Fetches the article SPA contents using Playwright.",
  inputs: {
    article: { description: "Article" }
  },
  outputs: {
    article: { description: "Article with content" }
  },
  run: () => { return; },
};

export const ExtractArticleContent: CodeNode = {
  id: "ExtractArticleContent",
  description: "Extracts the article content from the HTML and converts it to Markdown.",
  inputs: {
    article: { description: "Article" }
  },
  outputs: {
    article: { description: "Article with content" }
  },
  run: () => { return; },
};

export const SaveArticle: CodeNode = {
  id: "SaveArticle",
  description: "Saves the article to a file.",
  inputs: {
    article: { description: "Article" },
    path: { description: "Path prefix to save the article" }
  },
  outputs: {  },
  run: () => { return; },
};

