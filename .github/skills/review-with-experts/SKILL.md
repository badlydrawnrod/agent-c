---
name: review-with-experts
description: Review the codebase using an "ask the experts" approach. Use when you want a comprehensive evaluation of code quality, cohesion, and modularity from the perspective of software engineering experts.
---

# Review Criteria

## Primary Criteria
Please review this code for:
- cohesion
- modularity
- readability

These primary criteria are indicators of the quality of the codebase, but ultimately the design of the software should be assessed as 'State of the Art' if it is:
- well-structured and easy to understand
- easy to change and extend

## Additional Criteria
Additional criteria include:
- idiomatic Python 3.13
- cyclomatic complexity

These additional criteria are useful indicators, but should not be used as the primary basis for assessment. For example, if decreasing cyclomatic complexity requires sacrificing readability, then the code should not be changed.

# Approach
Use an "ask the experts" approach in which experts debate the codebase and reach a conclusion.

The experts should include:
- Dave Farley, who wrote the book Modern Software Engineering
- Will McGugan, the author of Textual
- Samuel Colvin, the author of pydantic_ai
- Guido van Rossum and other noted Python experts
