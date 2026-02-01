---
name: bazel-package-splitter
description: Analyze large Bazel packages and suggest physical refactoring into smaller, more maintainable sub-packages. Use this to improve build performance and code organization.
allowed-tools: Bash
---

# Bazel Package Splitter

Analyzes Bazel packages (directories with BUILD files) to identify overly large ones and suggests how to split them into focused sub-packages.

## Instructions for the Agent

1.  **Identify Large Packages**:
    *   Scan the codebase for BUILD files
    *   **Metrics to check**:
        *   Number of targets (rules) in the BUILD file
        *   Number of source files in the package directory
        *   Lines of code in the BUILD file
    *   **Thresholds** (suggest splitting if exceeded):
        *   >15-20 targets in one BUILD file
        *   >50 source files in one directory
        *   BUILD file >300 lines

2.  **Analyze Package Structure**:
    *   **Build Dependency Graph**: Within the package, identify which targets depend on which
    *   **Identify Clusters**: Group targets that:
        *   Depend on each other heavily
        *   Share similar naming patterns (e.g., `audio_*`, `render_*`)
        *   Belong to the same logical domain
    *   **Find Boundaries**: Look for targets with minimal internal dependencies (good candidates for extraction)

3.  **Suggest Package Splits**:
    *   For each large package, propose:
        *   **New Directory Structure**: Suggest sub-package names based on clusters
        *   **Target Migration**: Which targets move to which new sub-package
        *   **Visibility Updates**: How to update `visibility` attributes
        *   **Dependency Updates**: How other packages should update their `deps`

4.  **Generate Refactoring Report**:
    *   Create a markdown report: `bazel-package-split-report.md`
    *   **Include**:
        *   List of packages that should be split
        *   For each package:
            *   Current metrics (target count, LOC)
            *   Proposed new structure (directory tree)
            *   Migration steps (which files/targets move where)
            *   Updated BUILD file snippets
        *   Benefits: Improved build parallelism, clearer ownership, faster incremental builds

5.  **Save Report**:
    *   Save to `bazel-package-split-report.md`

## Example Prompt

"Analyze the `//src/engine` package and suggest how to split it."
