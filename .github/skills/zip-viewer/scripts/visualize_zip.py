#!/usr/bin/env python3
"""Generate an interactive collapsible tree visualization of a zip file's contents."""

import json
import sys
import webbrowser
import zipfile
from pathlib import Path
from collections import Counter

IGNORE = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}


def add_to_tree(tree, parts, size, ext):
    """
    Recursively add a path to the tree structure.
    tree: dict representing the current directory node
    parts: list of path components (e.g., ['folder', 'subfolder', 'file.txt'])
    size: size of the file
    ext: extension of the file
    """
    if not parts:
        return

    name = parts[0]
    
    # If it's a file (last part)
    if len(parts) == 1:
        tree["children"].append({"name": name, "size": size, "ext": ext})
        tree["size"] += size
        return

    # It's a directory
    # Find if this directory already exists in children
    child_dir = next((c for c in tree["children"] if c.get("children") is not None and c["name"] == name), None)
    
    if child_dir is None:
        child_dir = {"name": name, "children": [], "size": 0}
        tree["children"].append(child_dir)
    
    add_to_tree(child_dir, parts[1:], size, ext)
    tree["size"] += size # formatting fix: increment size of current dir with file size


def scan_zip(zip_path: Path, stats: dict) -> dict:
    file_name = zip_path.name
    root = {"name": file_name, "children": [], "size": 0}
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            for info in z.infolist():
                # Normalize path and parts
                path_str = info.filename.rstrip('/') # Remove trailing slash for dirs
                parts = path_str.split('/')
                
                # Check for ignore list in any part of the path
                if any(p in IGNORE or (p.startswith(".") and p != ".") for p in parts):
                    continue

                if info.is_dir():
                    stats["dirs"] += 1
                    # Ensure directory exists in tree even if empty
                    # (Logic handled implicitly by file addition, but could add explicit empty dir handling if needed)
                    # For now, we rely on files to populate dirs, or specific dir entries
                    # Let's explicitly add directory nodes if we encounter them
                    curr = root
                    for part in parts:
                        child = next((c for c in curr["children"] if c.get("children") is not None and c["name"] == part), None)
                        if child is None:
                            child = {"name": part, "children": [], "size": 0}
                            curr["children"].append(child)
                        curr = child
                    pass
                else:
                    # It's a file
                    size = info.file_size
                    ext = Path(info.filename).suffix.lower() or "(no ext)"
                    
                    stats["files"] += 1
                    stats["extensions"][ext] += 1
                    stats["ext_sizes"][ext] += size
                    
                    add_to_tree(root, parts, size, ext)
                    
    except zipfile.BadZipFile:
        print(f"Error: {zip_path} is not a valid zip file.")
        sys.exit(1)
    except FileNotFoundError:
        print(f"Error: File {zip_path} not found.")
        sys.exit(1)

    return root


def generate_html(data: dict, stats: dict, output: Path) -> None:
    ext_sizes = stats["ext_sizes"]
    total_size = sum(ext_sizes.values()) or 1
    sorted_exts = sorted(ext_sizes.items(), key=lambda x: -x[1])[:8]
    colors = {
        ".js": "#f7df1e",
        ".ts": "#3178c6",
        ".py": "#3776ab",
        ".go": "#00add8",
        ".rs": "#dea584",
        ".rb": "#cc342d",
        ".css": "#264de4",
        ".html": "#e34c26",
        ".json": "#6b7280",
        ".md": "#083fa1",
        ".yaml": "#cb171e",
        ".yml": "#cb171e",
        ".mdx": "#083fa1",
        ".tsx": "#3178c6",
        ".jsx": "#61dafb",
        ".sh": "#4eaa25",
        ".txt": "#f0f0f0",
        ".png": "#c0c0c0",
        ".jpg": "#c0c0c0",
        ".jpeg": "#c0c0c0",
    }
    lang_bars = "".join(
        f'<div class="bar-row"><span class="bar-label">{ext}</span>'
        f'<div class="bar" style="width:{(size/total_size)*100}%;background:{colors.get(ext,"#6b7280")}"></div>'
        f'<span class="bar-pct">{(size/total_size)*100:.1f}%</span></div>'
        for ext, size in sorted_exts
    )

    def fmt(b):
        if b < 1024:
            return f"{b} B"
        if b < 1048576:
            return f"{b/1024:.1f} KB"
        return f"{b/1048576:.1f} MB"

    html = f"""<!DOCTYPE html>
<html><head>
  <meta charset="utf-8"><title>Zip Content Explorer</title>
  <style>
    body {{ font: 14px/1.5 system-ui, sans-serif; margin: 0; background: #1a1a2e; color: #eee; }}
    .container {{ display: flex; height: 100vh; }}
    .sidebar {{ width: 280px; background: #252542; padding: 20px; border-right: 1px solid #3d3d5c; overflow-y: auto; flex-shrink: 0; }}
    .main {{ flex: 1; padding: 20px; overflow-y: auto; }}
    h1 {{ margin: 0 0 10px 0; font-size: 18px; }}
    h2 {{ margin: 20px 0 10px 0; font-size: 14px; color: #888; text-transform: uppercase; }}
    .stat {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #3d3d5c; }}
    .stat-value {{ font-weight: bold; }}
    .bar-row {{ display: flex; align-items: center; margin: 6px 0; }}
    .bar-label {{ width: 55px; font-size: 12px; color: #aaa; }}
    .bar {{ height: 18px; border-radius: 3px; }}
    .bar-pct {{ margin-left: 8px; font-size: 12px; color: #666; }}
    .tree {{ list-style: none; padding-left: 20px; }}
    details {{ cursor: pointer; }}
    summary {{ padding: 4px 8px; border-radius: 4px; }}
    summary:hover {{ background: #2d2d44; }}
    .folder {{ color: #ffd700; }}
    .file {{ display: flex; align-items: center; padding: 4px 8px; border-radius: 4px; }}
    .file:hover {{ background: #2d2d44; }}
    .size {{ color: #888; margin-left: auto; font-size: 12px; }}
    .dot {{ width: 8px; height: 8px; border-radius: 50%; margin-right: 8px; }}
  </style>
</head><body>
  <div class="container">
    <div class="sidebar">
      <h1>📊 Summary</h1>
      <div class="stat"><span>Files</span><span class="stat-value">{stats["files"]:,}</span></div>
      <div class="stat"><span>Directories</span><span class="stat-value">{stats["dirs"]:,}</span></div>
      <div class="stat"><span>Total size</span><span class="stat-value">{fmt(data["size"])}</span></div>
      <div class="stat"><span>File types</span><span class="stat-value">{len(stats["extensions"])}</span></div>
      <h2>By file type</h2>
      {lang_bars}
    </div>
    <div class="main">
      <h1>📁 {data["name"]}</h1>
      <ul class="tree" id="root"></ul>
    </div>
  </div>
  <script>
    const data = {json.dumps(data)};
    const colors = {json.dumps(colors)};
    function fmt(b) {{ if (b < 1024) return b + ' B'; if (b < 1048576) return (b/1024).toFixed(1) + ' KB'; return (b/1048576).toFixed(1) + ' MB'; }}
    function render(node, parent) {{
      if (node.children) {{
        const det = document.createElement('details');
        det.open = parent === document.getElementById('root');
        det.innerHTML = `<summary><span class="folder">📁 ${{node.name}}</span><span class="size">${{fmt(node.size)}}</span></summary>`;
        const ul = document.createElement('ul'); ul.className = 'tree';
        node.children.sort((a,b) => (b.children?1:0)-(a.children?1:0) || a.name.localeCompare(b.name));
        node.children.forEach(c => render(c, ul));
        det.appendChild(ul);
        const li = document.createElement('li'); li.appendChild(det); parent.appendChild(li);
      }} else {{
        const li = document.createElement('li'); li.className = 'file';
        li.innerHTML = `<span class="dot" style="background:${{colors[node.ext]||'#6b7280'}}"></span>${{node.name}}<span class="size">${{fmt(node.size)}}</span>`;
        parent.appendChild(li);
      }}
    }}
    data.children.forEach(c => render(c, document.getElementById('root')));
  </script>
</body></html>"""
    output.write_text(html, encoding='utf-8')


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: visualize_zip.py <path_to_zip_file>")
        sys.exit(1)
        
    target = Path(sys.argv[1]).resolve()
    stats = {"files": 0, "dirs": 0, "extensions": Counter(), "ext_sizes": Counter()}
    data = scan_zip(target, stats)
    out = Path("zip-content-map.html")
    generate_html(data, stats, out)
    print(f"Generated {out.absolute()}")
    webbrowser.open(f"file://{out.absolute()}")
