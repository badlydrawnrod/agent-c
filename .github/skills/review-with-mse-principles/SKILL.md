---
name: review-with-mse-principles
description: Review codebase using Dave Farley's "Modern Software Engineering" principles. Use when assessing if the software design is optimized for learning and managing complexity.
---

# Modern Software Engineering Review (Dave Farley Principles)

## Context

Review this codebase using the principles from Dave Farley's "Modern Software Engineering". The goal is to assess whether the software design enables effective software engineering practices.

## Core Principles

Dave Farley argues that good software design must be:

1. **Optimized for Learning**
2. **Optimized for Managing Complexity**

These two principles underpin all other engineering practices.

## Evaluation Framework

### 1. Optimized for Learning

#### Questions to Answer:

**Discoverability**
- How quickly can a new developer build a mental model of the system?
- Are architectural patterns obvious from the code structure?
- Can you find where to make changes without asking for help?

**Consistency**
- Do similar problems have similar solutions throughout the codebase?
- Are naming conventions predictable and meaningful?
- Do abstractions follow consistent patterns?

**Feedback Loops**
- How fast can you verify a change works? (seconds, minutes, hours?)
- Are tests easy to run and understand?
- Do error messages guide you to solutions?

**Documentation as Code**
- Does the code structure communicate intent?
- Are type signatures informative?
- Do module boundaries make sense?

**Safe Experimentation**
- Can you try changes without fear of breaking things?
- Is it easy to revert mistakes?
- Do tests catch regressions quickly?

#### Assessment Criteria:
- **Excellent (9-10)**: New developers productive in < 1 day; patterns obvious; fast feedback
- **Good (7-8)**: Productive in 2-3 days; some exploration needed; decent feedback
- **Fair (5-6)**: Productive in 1-2 weeks; requires significant guidance; slow feedback
- **Poor (1-4)**: Productive in 1+ months; patterns unclear; minimal feedback

---

### 2. Optimized for Managing Complexity

#### Questions to Answer:

**Modularity**
- Can you understand one part without understanding the whole?
- Are dependencies unidirectional and minimal?
- Can components be tested in isolation?

**Coupling & Cohesion**
- Do modules have single, clear responsibilities?
- Are boundaries between modules well-defined?
- Can you change one module without affecting others?

**Abstraction Quality**
- Do abstractions hide the right details?
- Are interfaces minimal and focused?
- Do abstractions prevent or enable complexity?

**Testability**
- Can you test business logic without frameworks?
- Are side effects isolated and controlled?
- Can you reason about correctness locally?

**Changeability**
- How many files must you touch for typical changes?
- Are extension points obvious?
- Does adding features require modifying existing code (vs. adding new)?

**State Management**
- Is state localized and controlled?
- Are mutations explicit and traceable?
- Can you reason about state without global analysis?

#### Assessment Criteria:
- **Excellent (9-10)**: High cohesion; minimal coupling; local reasoning possible; easy changes
- **Good (7-8)**: Clear modules; some coupling; mostly local reasoning; manageable changes
- **Fair (5-6)**: Mixed responsibilities; moderate coupling; requires system knowledge; difficult changes
- **Poor (1-4)**: Tangled concerns; high coupling; global reasoning required; risky changes

---

## Supporting Practices

Farley emphasizes these practices as consequences of the two core principles:

### Working Iteratively
- **Can you make small, safe changes?**
- Are there clear, incremental steps for new features?
- Can you commit partial work safely?

### Empiricism & Feedback
- **What evidence exists that the design works?**
- Are there automated tests demonstrating correctness?
- Do tests run fast enough to guide development?
- Are there metrics or observability for production behavior?

### Incrementalism
- **Does the architecture support evolutionary design?**
- Can you add features without rewriting?
- Are there versioning/compatibility strategies?

### Experimentation
- **Is it safe to try new approaches?**
- Can you prototype quickly?
- Are failures cheap and informative?

---

## Review Format

### Part 1: Learning Optimization (Score: __/10)

Provide evidence-based assessment:

1. **Time to Productivity**: Estimate hours for a competent developer to:
   - Understand architecture: __ hours
   - Make first meaningful change: __ hours
   - Be fully productive: __ days

2. **Pattern Consistency**: Rate 1-10 and provide examples
   - Examples of consistent patterns:
   - Examples of inconsistency (if any):

3. **Feedback Speed**: Measure actual times
   - Run full test suite: __ seconds
   - Run subset of tests: __ seconds
   - Build and run locally: __ seconds

4. **Safe Experimentation**: Rate 1-10
   - Evidence of safety mechanisms:
   - Areas of concern:

**Overall Learning Score: __/10**

---

### Part 2: Complexity Management (Score: __/10)

Provide evidence-based assessment:

1. **Modularity**: Rate 1-10 and provide examples
   - Example of good module boundary:
   - Example of unclear boundary (if any):
   - Dependency graph complexity: (simple/moderate/complex)

2. **Coupling Analysis**: Rate 1-10
   - Examples of low coupling:
   - Examples of high coupling (if any):
   - Can you test core logic without UI? (yes/no)

3. **Cohesion Analysis**: Rate 1-10
   - Examples of high cohesion:
   - Examples of scattered responsibility (if any):

4. **Change Localization**: Measure actual impact
   - Add new tool: Touch __ files in __ modules
   - Add new command: Touch __ files in __ modules
   - Add new UI: Touch __ files in __ modules
   - Change LLM provider: Touch __ files in __ modules

5. **State Management**: Rate 1-10
   - Global state instances: __
   - Mutable shared state: (none/minimal/moderate/extensive)
   - Evidence of controlled state:

**Overall Complexity Score: __/10**

---

### Part 3: Engineering Practices (Score: __/10)

1. **Iterative Development**: Rate 1-10
   - Typical commit size: (small/medium/large)
   - Feature branch strategy: (clear/unclear)
   - Can you safely commit partial work? (yes/no)

2. **Empiricism**: Rate 1-10
   - Test coverage: __%
   - Test quality: (high/medium/low)
   - Evidence-based decisions: (yes/no)

3. **Incrementalism**: Rate 1-10
   - Can extend without modifying? (yes/no)
   - Versioning strategy: (clear/unclear)
   - Technical debt level: (low/medium/high)

4. **Experimentation**: Rate 1-10
   - Prototype speed: (fast/medium/slow)
   - Failure cost: (cheap/moderate/expensive)
   - Architecture flexibility: (high/medium/low)

**Overall Practices Score: __/10**

---

## Final Assessment

### Quantitative Summary

| Principle/Practice          | Score | Weight | Weighted |
|----------------------------|-------|--------|----------|
| Optimized for Learning     | __/10 | 35%    | __       |
| Managing Complexity        | __/10 | 35%    | __       |
| Engineering Practices      | __/10 | 30%    | __       |
| **Total**                  |       | 100%   | **__/10**|

### Qualitative Assessment

**What Makes This Design Excellent (or not)?**
- [Provide specific examples]

**Key Strengths:**
1. 
2. 
3. 

**Key Weaknesses (if any):**
1. 
2. 
3. 

**Alignment with Farley's Philosophy:**
- Does this codebase embody "software engineering as learning"? (yes/no/partially)
- Does this codebase make complexity manageable? (yes/no/partially)
- Would Farley recommend this as a reference implementation? (yes/no/maybe)

---

## Actionable Recommendations

Based on the assessment, provide **specific, actionable** recommendations:

### High Priority (Significant Impact on Learning/Complexity)
1. 
2. 
3. 

### Medium Priority (Incremental Improvements)
1. 
2. 
3. 

### Low Priority (Polish & Refinement)
1. 
2. 
3. 

---

## Dave Farley's Likely Assessment

If Dave Farley himself were reviewing this codebase, what would he say?

**Opening Statement:**
[What would be his first impression?]

**Specific Praise:**
[What specific practices would he highlight as exemplary?]

**Concerns (if any):**
[What would give him pause?]

**Overall Verdict:**
[Would he recommend this as a case study? Why or why not?]

**Rating (his likely score): __/10**

---

## Conclusion

### Summary Statement
[One paragraph summarizing whether this codebase exemplifies "Modern Software Engineering" principles]

### Evidence of Engineering Excellence
[Cite specific examples from the code that demonstrate the principles]

### Path Forward
[If perfect score: how to maintain excellence]
[If not perfect: prioritized improvement roadmap]

---

**Review Completed By:** [Name]  
**Date:** [Date]  
**Time Spent on Review:** [Hours]
