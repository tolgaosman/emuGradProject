---
name: claude-mem
description: >-
  Use this skill to structure context, manage long-term memory, and maintain state 
  efficiently across multiple agent sessions or LLM interactions.
---

# Memory Management (claude-mem)

Ensure critical project context is preserved and easily retrievable.

## Techniques
1. **Knowledge Graphing**: Document entities, relationships, and architectural decisions in standardized Markdown files (e.g., in a `.docs` or `knowledge/` directory).
2. **Context Summarization**: Periodically summarize long discussions or complex state into concise state files.
3. **Tagging and Indexing**: Use clear headings, keywords, and tags so that future searches (e.g., `grep`) can easily find the context.
4. **Decision Records**: Maintain Architecture Decision Records (ADRs) to remember *why* a decision was made, not just *what* it is.
5. **State Hydration**: When starting a new task, explicitly read these memory files to hydrate context before proceeding.
