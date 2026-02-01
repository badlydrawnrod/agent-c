#!/usr/bin/env python3
"""Generate an interactive class diagram from Python source files."""

import ast
import json
import sys
import webbrowser
from pathlib import Path
from typing import Any

IGNORE = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".pytest_cache"}


class ClassVisitor(ast.NodeVisitor):
    """Extract class information from Python AST."""

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.classes = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(f"{self._get_attr_name(base)}")

        methods = []
        attributes = []
        is_protocol = any(
            (isinstance(b, ast.Name) and b.id == "Protocol") or
            (isinstance(b, ast.Attribute) and b.attr == "Protocol")
            for b in node.bases
        )
        is_abc = any("ABC" in self._get_base_name(b) for b in node.bases)

        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                # Extract method signature
                args = [arg.arg for arg in item.args.args if arg.arg != "self"]
                method_sig = f"{item.name}({', '.join(args)})"
                is_private = item.name.startswith("_")
                methods.append({"name": method_sig, "private": is_private})
            elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                # Class variable with type annotation
                attr_name = item.target.id
                is_private = attr_name.startswith("_")
                attributes.append({"name": attr_name, "private": is_private})
            elif isinstance(item, ast.Assign):
                # Class variable without type annotation
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        attr_name = target.id
                        is_private = attr_name.startswith("_")
                        attributes.append({"name": attr_name, "private": is_private})

        self.classes.append({
            "name": node.name,
            "module": self.filepath.stem,
            "file": str(self.filepath),
            "bases": bases,
            "methods": methods,
            "attributes": attributes,
            "is_protocol": is_protocol,
            "is_abc": is_abc,
            "line": node.lineno,
        })
        self.generic_visit(node)

    def _get_attr_name(self, node: ast.Attribute) -> str:
        """Get full attribute name like module.Class."""
        parts = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))

    def _get_base_name(self, node: Any) -> str:
        """Get base class name as string."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_attr_name(node)
        return ""


def scan_directory(path: Path) -> list[dict]:
    """Scan directory for Python files and extract class information."""
    all_classes = []

    for py_file in path.rglob("*.py"):
        # Skip ignored directories
        if any(ignored in py_file.parts for ignored in IGNORE):
            continue

        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
            visitor = ClassVisitor(py_file.relative_to(path) if py_file.is_relative_to(path) else py_file)
            visitor.visit(tree)
            all_classes.extend(visitor.classes)
        except (SyntaxError, UnicodeDecodeError):
            # Skip files with syntax errors or encoding issues
            continue

    return all_classes


def calculate_hierarchical_layout(classes: list[dict]) -> dict[str, dict[str, float]]:
    """Calculate hierarchical positions for classes based on inheritance."""
    # Build inheritance graph
    class_map = {cls["name"]: cls for cls in classes}
    children_map = {cls["name"]: [] for cls in classes}
    parent_map = {cls["name"]: [] for cls in classes}
    
    for cls in classes:
        for base in cls["bases"]:
            base_short = base.split('.')[-1]
            if base_short in class_map:
                children_map[base_short].append(cls["name"])
                parent_map[cls["name"]].append(base_short)
    
    # Calculate levels (topological sort by depth)
    levels = {}
    
    def calculate_level(name: str, visited: set) -> int:
        if name in levels:
            return levels[name]
        if name in visited:  # Circular dependency
            return 0
        visited.add(name)
        
        parents = parent_map.get(name, [])
        if not parents:
            levels[name] = 0
            return 0
        
        max_parent_level = max(calculate_level(p, visited.copy()) for p in parents)
        levels[name] = max_parent_level + 1
        return levels[name]
    
    for cls in classes:
        calculate_level(cls["name"], set())
    
    # Group by level
    level_groups = {}
    for name, level in levels.items():
        if level not in level_groups:
            level_groups[level] = []
        level_groups[level].append(name)
    
    # Position classes
    positions = {}
    vertical_spacing = 280
    horizontal_spacing = 280
    start_x = 50
    start_y = 50
    
    for level in sorted(level_groups.keys()):
        names = level_groups[level]
        # Center this level horizontally
        total_width = len(names) * horizontal_spacing
        level_start_x = start_x + (5 * horizontal_spacing - total_width) // 2
        
        for i, name in enumerate(sorted(names)):
            positions[name] = {
                "x": level_start_x + i * horizontal_spacing,
                "y": start_y + level * vertical_spacing
            }
    
    # Handle classes without relationships (orphans)
    orphan_y = start_y + (max(level_groups.keys()) + 2) * vertical_spacing if level_groups else start_y
    orphan_x = start_x
    orphan_count = 0
    for cls in classes:
        if cls["name"] not in positions:
            positions[cls["name"]] = {
                "x": orphan_x + (orphan_count % 5) * horizontal_spacing,
                "y": orphan_y + (orphan_count // 5) * vertical_spacing
            }
            orphan_count += 1
    
    return positions


def generate_html(classes: list[dict], output: Path) -> None:
    """Generate interactive HTML visualization."""
    # Calculate hierarchical layout
    positions = calculate_hierarchical_layout(classes)
    
    classes_json = json.dumps(classes)
    positions_json = json.dumps(positions)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Class Diagram</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #1e293b;
      color: #e2e8f0;
      overflow: hidden;
    }}
    #canvas {{
      width: 100vw;
      height: 100vh;
      cursor: grab;
      position: relative;
    }}
    #canvas.dragging {{ cursor: grabbing; }}
    .class-box {{
      position: absolute;
      background: #334155;
      border: 2px solid #475569;
      border-radius: 8px;
      min-width: 200px;
      box-shadow: 0 4px 6px rgba(0,0,0,0.3);
      cursor: move;
    }}
    .class-box.protocol {{
      border-color: #8b5cf6;
      background: #3730a3;
    }}
    .class-box.abc {{
      border-color: #06b6d4;
      background: #164e63;
    }}
    .class-header {{
      background: #475569;
      padding: 12px;
      font-weight: bold;
      border-radius: 6px 6px 0 0;
      text-align: center;
      font-size: 14px;
    }}
    .protocol .class-header {{
      background: #6d28d9;
    }}
    .abc .class-header {{
      background: #0891b2;
    }}
    .class-section {{
      padding: 8px 12px;
      border-top: 1px solid #475569;
      font-size: 12px;
    }}
    .class-section div {{
      padding: 2px 0;
      font-family: 'Courier New', monospace;
    }}
    .private {{ color: #94a3b8; }}
    .class-meta {{
      padding: 6px 12px;
      font-size: 11px;
      color: #94a3b8;
      border-top: 1px solid #475569;
      font-style: italic;
    }}
    svg {{
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      pointer-events: none;
      z-index: 0;
    }}
    .inheritance-line {{
      stroke: #60a5fa;
      stroke-width: 2;
      fill: none;
      marker-end: url(#arrowhead);
    }}
    #info {{
      position: fixed;
      top: 10px;
      right: 10px;
      background: rgba(30, 41, 59, 0.95);
      padding: 15px;
      border-radius: 8px;
      border: 1px solid #475569;
      font-size: 13px;
      max-width: 300px;
      z-index: 1000;
    }}
    #info h3 {{ margin-bottom: 8px; color: #60a5fa; }}
    #info div {{ margin: 4px 0; }}
  </style>
</head>
<body>
  <div id="canvas">
    <svg>
      <defs>
        <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
          <polygon points="0 0, 10 3, 0 6" fill="#60a5fa" />
        </marker>
      </defs>
      <g id="lines"></g>
    </svg>
  </div>
  <div id="info">
    <h3>Class Diagram</h3>
    <div><strong>Classes:</strong> <span id="class-count">0</span></div>
    <div><strong>Protocols:</strong> <span id="protocol-count">0</span></div>
    <div style="margin-top: 10px; font-size: 11px; color: #94a3b8;">
      Drag classes to rearrange<br>
      Click and drag background to pan
    </div>
  </div>

  <script>
    const classes = {classes_json};
    const initialPositions = {positions_json};
    const canvas = document.getElementById('canvas');
    const linesGroup = document.getElementById('lines');
    
    let offsetX = 0, offsetY = 0;
    let isDraggingCanvas = false;
    let draggedBox = null;
    let startX = 0, startY = 0;

    // Use hierarchical layout from Python
    const positions = new Map(Object.entries(initialPositions));

    // Create class boxes
    classes.forEach(cls => {{
      const box = document.createElement('div');
      box.className = 'class-box' + 
        (cls.is_protocol ? ' protocol' : '') + 
        (cls.is_abc ? ' abc' : '');
      
      const pos = positions.get(cls.name);
      box.style.left = pos.x + 'px';
      box.style.top = pos.y + 'px';

      let html = `<div class="class-header">${{cls.name}}</div>`;
      
      if (cls.attributes.length > 0) {{
        html += '<div class="class-section">';
        cls.attributes.forEach(attr => {{
          const className = attr.private ? 'private' : '';
          html += `<div class="${{className}}">${{attr.name}}</div>`;
        }});
        html += '</div>';
      }}

      if (cls.methods.length > 0) {{
        html += '<div class="class-section">';
        cls.methods.forEach(method => {{
          const className = method.private ? 'private' : '';
          html += `<div class="${{className}}">${{method.name}}</div>`;
        }});
        html += '</div>';
      }}

      html += `<div class="class-meta">${{cls.module}}.py:${{cls.line}}</div>`;
      box.innerHTML = html;
      box.dataset.className = cls.name;
      box.setAttribute('data-class-name', cls.name);

      box.addEventListener('mousedown', (e) => {{
        if (e.target.closest('.class-box')) {{
          e.stopPropagation();
          draggedBox = box;
          startX = e.clientX - box.offsetLeft;
          startY = e.clientY - box.offsetTop;
          box.style.zIndex = 1000;
        }}
      }});

      canvas.appendChild(box);
    }});

    // Draw inheritance lines
    function drawLines() {{
      linesGroup.innerHTML = '';
      classes.forEach(cls => {{
        cls.bases.forEach(base => {{
          const baseShort = base.split('.').pop();
          const fromPos = positions.get(baseShort);
          const toPos = positions.get(cls.name);
          
          if (fromPos && toPos) {{
            // Get the actual DOM elements to calculate heights
            const fromBox = document.querySelector(`[data-class-name="${{baseShort}}"]`);
            const toBox = document.querySelector(`[data-class-name="${{cls.name}}"]`);
            
            const fromHeight = fromBox ? fromBox.offsetHeight : 100;
            const toHeight = toBox ? toBox.offsetHeight : 100;
            
            // Line from bottom center of parent to top center of child
            const fromX = fromPos.x + 100 + offsetX;
            const fromY = fromPos.y + fromHeight + offsetY;
            const toX = toPos.x + 100 + offsetX;
            const toY = toPos.y + offsetY;
            
            const line = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            line.setAttribute('d', `M ${{fromX}} ${{fromY}} L ${{toX}} ${{toY}}`);
            line.setAttribute('class', 'inheritance-line');
            linesGroup.appendChild(line);
          }}
        }});
      }});
    }}

    // Canvas dragging
    canvas.addEventListener('mousedown', (e) => {{
      if (!e.target.closest('.class-box')) {{
        isDraggingCanvas = true;
        canvas.classList.add('dragging');
        startX = e.clientX - offsetX;
        startY = e.clientY - offsetY;
      }}
    }});

    document.addEventListener('mousemove', (e) => {{
      if (isDraggingCanvas) {{
        offsetX = e.clientX - startX;
        offsetY = e.clientY - startY;
        document.querySelectorAll('.class-box').forEach(box => {{
          const pos = positions.get(box.dataset.className);
          box.style.left = (pos.x + offsetX) + 'px';
          box.style.top = (pos.y + offsetY) + 'px';
        }});
        drawLines();
      }} else if (draggedBox) {{
        const newX = e.clientX - startX;
        const newY = e.clientY - startY;
        draggedBox.style.left = newX + 'px';
        draggedBox.style.top = newY + 'px';
        positions.set(draggedBox.dataset.className, {{ x: newX - offsetX, y: newY - offsetY }});
        drawLines();
      }}
    }});

    document.addEventListener('mouseup', () => {{
      isDraggingCanvas = false;
      canvas.classList.remove('dragging');
      if (draggedBox) {{
        draggedBox.style.zIndex = '';
        draggedBox = null;
      }}
    }});

    // Update stats
    document.getElementById('class-count').textContent = classes.length;
    document.getElementById('protocol-count').textContent = 
      classes.filter(c => c.is_protocol).length;

    // Initial draw
    drawLines();
  </script>
</body>
</html>"""

    output.write_text(html, encoding='utf-8')


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    
    if not target.exists():
        print(f"Error: Path '{target}' does not exist")
        sys.exit(1)

    print(f"Scanning {target} for Python classes...")
    classes = scan_directory(target)
    
    if not classes:
        print("No classes found in the specified directory")
        sys.exit(1)

    print(f"Found {len(classes)} classes")
    
    out = Path("class-diagram.html")
    generate_html(classes, out)
    print(f"Generated {out.absolute()}")
    webbrowser.open(f"file://{out.absolute()}")
