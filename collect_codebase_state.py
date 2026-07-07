"""
collect_codebase_state.py
=========================
Structured-state exporter for the "codebase-onboarding" skill.

It dumps the facts you need to onboard to an unfamiliar repo BEFORE you trust
the README or start guessing: package manifests, framework fingerprints, entry
points, a pruned directory tree, config/tooling, test structure, language
breakdown, naming + git conventions, and a list of flagged "findings" (missing
manifest, ambiguous package manager, no tests, no CI, ...).

This is the codebase analogue of collect_motion_state.py: reconnaissance first,
opinions later. Where the Blender exporter must run inside Blender's interpreter
(because bpy is unavailable elsewhere), this one is the opposite on purpose --
it uses only the Python standard library so it runs anywhere, on any repo,
with nothing to install:

    python collect_codebase_state.py -- --root . --out codebase_state.json

The lone "--" is optional; every flag also works without it:

    python collect_codebase_state.py --root ./my-project --max-files 40000

Read-only. It never modifies the analyzed repo; the only thing it writes is the
output JSON (default: ./codebase_state.json).
"""

import os
import sys
import re
import json
import argparse
import subprocess
from collections import Counter, defaultdict


# ----------------------------------------------------------------------------
# Argument parsing (accept a lone "--" separator to mirror the Blender script)
# ----------------------------------------------------------------------------

def parse_args():
    argv = sys.argv[1:]
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    p = argparse.ArgumentParser(description="Export codebase onboarding state to JSON.")
    p.add_argument("--root", default=".", help="Repository root to analyze")
    p.add_argument("--out", default="codebase_state.json", help="Output JSON path")
    p.add_argument("--max-depth", type=int, default=2,
                   help="Directory-tree snapshot depth (default 2 levels)")
    p.add_argument("--max-files", type=int, default=50000,
                   help="Stop walking after this many files (guards huge repos)")
    p.add_argument("--git-log", type=int, default=20,
                   help="How many recent commits to sample for conventions")
    return p.parse_args(argv)


# ----------------------------------------------------------------------------
# Noise we never descend into or count
# ----------------------------------------------------------------------------

IGNORE_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", "out", "target",
    "__pycache__", ".next", ".nuxt", ".venv", "venv", "env", ".mypy_cache",
    ".pytest_cache", ".gradle", ".idea", ".vscode", "coverage", ".turbo",
    "bin", "obj", ".terraform", ".cache", "Pods", ".dart_tool",
}

# Extensions we treat as source for language + naming analysis
LANG_BY_EXT = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".go": "Go", ".rs": "Rust",
    ".java": "Java", ".kt": "Kotlin", ".rb": "Ruby", ".php": "PHP",
    ".cs": "C#", ".fs": "F#", ".cpp": "C++", ".cc": "C++", ".c": "C",
    ".h": "C/C++ header", ".hpp": "C++ header", ".swift": "Swift",
    ".scala": "Scala", ".ex": "Elixir", ".exs": "Elixir", ".dart": "Dart",
    ".sh": "Shell", ".sql": "SQL", ".vue": "Vue", ".svelte": "Svelte",
    ".md": "Markdown", ".json": "JSON", ".yml": "YAML", ".yaml": "YAML",
}


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------

def read_text(path, limit=200_000):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except (OSError, UnicodeError):
        return None

def load_json(path):
    txt = read_text(path)
    if txt is None:
        return None
    try:
        return json.loads(txt)
    except (json.JSONDecodeError, ValueError):
        return None

def rel(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")

def run_git(root, args):
    """Run a git command in root; return stripped stdout or None on any failure."""
    try:
        out = subprocess.run(
            ["git", "-C", root] + args,
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode != 0:
            return None
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


# ----------------------------------------------------------------------------
# One traversal: collect every file path (pruned), capped, with counts
# ----------------------------------------------------------------------------

def walk_repo(root, max_files):
    files = []
    truncated = False
    for dirpath, dirnames, filenames in os.walk(root):
        # prune noise in place so os.walk does not descend into it.
        # Note: only the real ".git" dir is dropped (it is in IGNORE_DIRS);
        # ".github" must survive so CI workflows are still detected.
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for name in filenames:
            files.append(os.path.join(dirpath, name))
            if len(files) >= max_files:
                truncated = True
                return files, truncated
    return files, truncated


# ----------------------------------------------------------------------------
# Phase 1: reconnaissance -- manifests, frameworks, entry points, tooling, tests
# ----------------------------------------------------------------------------

# ecosystem -> the manifest filename(s) that prove it
MANIFESTS = {
    "node":   ["package.json"],
    "go":     ["go.mod"],
    "rust":   ["Cargo.toml"],
    "python": ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"],
    "maven":  ["pom.xml"],
    "gradle": ["build.gradle", "build.gradle.kts"],
    "ruby":   ["Gemfile"],
    "php":    ["composer.json"],
    "elixir": ["mix.exs"],
    "dart":   ["pubspec.yaml"],
    "dotnet": [".csproj", ".fsproj", ".sln"],
}

# lockfiles that reveal which package manager is actually in use
LOCKFILES = {
    "npm": "package-lock.json", "yarn": "yarn.lock", "pnpm": "pnpm-lock.yaml",
    "bun": "bun.lockb", "pip": "requirements.txt", "poetry": "poetry.lock",
    "pipenv": "Pipfile.lock", "cargo": "Cargo.lock", "go": "go.sum",
    "composer": "composer.lock", "bundler": "Gemfile.lock",
}

# filename (or glob-ish suffix) -> framework label. Loose on purpose.
FRAMEWORK_FILES = {
    "next.config": "Next.js", "nuxt.config": "Nuxt", "angular.json": "Angular",
    "vite.config": "Vite", "svelte.config": "Svelte", "remix.config": "Remix",
    "astro.config": "Astro", "gatsby-config": "Gatsby", "manage.py": "Django",
    "artisan": "Laravel", "config/routes.rb": "Rails",
}
# dependency name (in package.json / requirements) -> framework label
FRAMEWORK_DEPS = {
    "next": "Next.js", "react": "React", "vue": "Vue", "svelte": "Svelte",
    "@angular/core": "Angular", "express": "Express", "fastify": "Fastify",
    "nestjs": "NestJS", "@nestjs/core": "NestJS", "django": "Django",
    "flask": "Flask", "fastapi": "FastAPI", "rails": "Rails",
    "spring-boot": "Spring Boot",
}

ENTRY_HINTS = ("main.", "index.", "app.", "server.", "cli.", "__main__.")

CONFIG_FILES = {
    "linters":  [".eslintrc", ".flake8", ".ruff.toml", "ruff.toml", ".rubocop.yml",
                 ".golangci.yml", ".golangci.yaml"],
    "formatters": [".prettierrc", ".editorconfig", "rustfmt.toml"],
    "typescript": ["tsconfig.json"],
    "build":    ["Makefile", "makefile", "Taskfile.yml", "justfile"],
    "docker":   ["Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yaml"],
    "env":      [".env.example", ".env.sample", ".env.template"],
    "docs":     ["README.md", "README.rst", "CONTRIBUTING.md"],
    "license":  ["LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"],
}

TEST_MARKERS = ("test", "spec", "__tests__")


def recon(root, files):
    basenames = {rel(root, f): os.path.basename(f) for f in files}
    all_names = list(basenames.values())

    # -- manifests --------------------------------------------------------
    manifests = {}
    for eco, marks in MANIFESTS.items():
        hits = sorted({
            r for r, b in basenames.items()
            if b in marks or any(b.endswith(m) for m in marks if m.startswith("."))
        })
        if hits:
            manifests[eco] = hits

    # -- package managers (from lockfiles present) ------------------------
    package_managers = sorted({
        pm for pm, lock in LOCKFILES.items() if lock in all_names
    })

    # -- frameworks (files) -----------------------------------------------
    frameworks = set()
    for r in basenames:
        for frag, label in FRAMEWORK_FILES.items():
            if r.endswith(frag) or os.path.basename(r).startswith(frag):
                frameworks.add(label)

    # -- frameworks (dependencies) ----------------------------------------
    deps = collect_dependencies(root, basenames)
    for dep in deps:
        low = dep.lower()
        for key, label in FRAMEWORK_DEPS.items():
            if low == key or low.startswith(key):
                frameworks.add(label)

    # -- entry points -----------------------------------------------------
    entry_points = sorted({
        r for r, b in basenames.items()
        if any(b.startswith(h) for h in ENTRY_HINTS)
        and b.rsplit(".", 1)[-1] in ("py", "js", "ts", "jsx", "tsx", "go", "rs", "rb")
    })[:25]

    # -- config / tooling -------------------------------------------------
    tooling = {}
    for group, names in CONFIG_FILES.items():
        found = sorted({
            r for r, b in basenames.items()
            if b in names or any(b.startswith(n) for n in names)
        })
        tooling[group] = found

    # -- CI ---------------------------------------------------------------
    ci = sorted({
        r for r in basenames
        if r.startswith(".github/workflows/")
        or os.path.basename(r) in (".gitlab-ci.yml", ".travis.yml", "azure-pipelines.yml", "Jenkinsfile")
    })

    # -- tests ------------------------------------------------------------
    test_files = sorted({
        r for r in basenames
        if any(m in r.lower() for m in TEST_MARKERS)
    })

    return {
        "manifests": manifests,
        "package_managers": package_managers,
        "frameworks": sorted(frameworks),
        "key_dependencies": sorted(deps)[:40],
        "entry_points": entry_points,
        "tooling": tooling,
        "ci": ci,
        "test_files_sampled": test_files[:40],
        "test_file_count": len(test_files),
    }


def collect_dependencies(root, basenames):
    """Best-effort dependency names from package.json + python requirement files."""
    deps = set()
    # package.json
    for r, b in basenames.items():
        if b == "package.json":
            data = load_json(os.path.join(root, r))
            if isinstance(data, dict):
                for field in ("dependencies", "devDependencies"):
                    section = data.get(field)
                    if isinstance(section, dict):
                        deps.update(section.keys())
        elif b == "requirements.txt":
            txt = read_text(os.path.join(root, r)) or ""
            for line in txt.splitlines():
                name = re.split(r"[<>=!~\[; ]", line.strip(), 1)[0]
                if name and not name.startswith("#"):
                    deps.add(name)
    return deps


# ----------------------------------------------------------------------------
# Phase 1b: pruned directory tree snapshot (top N levels)
# ----------------------------------------------------------------------------

def directory_tree(root, max_depth):
    tree = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
        depth = rel(root, dirpath).count("/") if rel(root, dirpath) != "." else 0
        if depth >= max_depth:
            dirnames[:] = []
        r = rel(root, dirpath)
        tree[r if r != "." else "(root)"] = {
            "dirs": sorted(dirnames),
            "file_count": len(filenames),
        }
    return tree


# ----------------------------------------------------------------------------
# Phase 2: language breakdown (by file count and bytes)
# ----------------------------------------------------------------------------

def language_breakdown(root, files):
    by_count = Counter()
    by_bytes = Counter()
    for f in files:
        ext = os.path.splitext(f)[1].lower()
        lang = LANG_BY_EXT.get(ext)
        if not lang:
            continue
        by_count[lang] += 1
        try:
            by_bytes[lang] += os.path.getsize(f)
        except OSError:
            pass
    top_count = by_count.most_common(10)
    top_bytes = by_bytes.most_common(10)
    return {
        "primary_language": top_bytes[0][0] if top_bytes else None,
        "by_file_count": [{"language": l, "files": n} for l, n in top_count],
        "by_bytes": [{"language": l, "bytes": n} for l, n in top_bytes],
    }


# ----------------------------------------------------------------------------
# Phase 3: convention detection (naming + git)
# ----------------------------------------------------------------------------

def classify_case(stem):
    if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)+", stem):
        return "kebab-case"
    if re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)+", stem):
        return "snake_case"
    if re.fullmatch(r"[A-Z][a-zA-Z0-9]*", stem) and any(c.isupper() for c in stem[1:]):
        return "PascalCase"
    if re.fullmatch(r"[a-z][a-zA-Z0-9]*", stem) and any(c.isupper() for c in stem):
        return "camelCase"
    return None

def naming_conventions(root, files):
    counts = Counter()
    for f in files:
        ext = os.path.splitext(f)[1].lower()
        if ext not in LANG_BY_EXT or LANG_BY_EXT[ext] in ("Markdown", "JSON", "YAML"):
            continue
        stem = os.path.splitext(os.path.basename(f))[0]
        style = classify_case(stem)
        if style:
            counts[style] += 1
    ranked = counts.most_common()
    return {
        "file_naming_distribution": [{"style": s, "count": n} for s, n in ranked],
        "dominant_file_naming": ranked[0][0] if ranked else None,
    }

def git_conventions(root, log_n):
    if run_git(root, ["rev-parse", "--is-inside-work-tree"]) != "true":
        return {"available": False, "note": "Not a git work tree."}
    depth = run_git(root, ["rev-list", "--count", "HEAD"])
    if depth is not None and depth.isdigit() and int(depth) < 2:
        return {"available": False,
                "note": "Git history unavailable or too shallow to detect conventions."}
    current = run_git(root, ["branch", "--show-current"])
    branches = run_git(root, ["for-each-ref", "--sort=-committerdate",
                              "--format=%(refname:short)", "refs/heads", "--count=10"])
    subjects = run_git(root, ["log", f"-{log_n}", "--pretty=%s"])
    subj_list = subjects.splitlines() if subjects else []

    # loose conventional-commit detection: "type(scope): summary"
    conv = sum(1 for s in subj_list if re.match(r"^[a-z]+(\([^)]+\))?!?:\s", s))
    style = "conventional-commits" if subj_list and conv / len(subj_list) > 0.5 else "freeform"

    return {
        "available": True,
        "current_branch": current,
        "recent_branches": branches.splitlines() if branches else [],
        "recent_commit_subjects": subj_list[:log_n],
        "commit_style": style,
    }


# ----------------------------------------------------------------------------
# Findings: flag what reconnaissance could NOT confidently resolve
# ----------------------------------------------------------------------------

def diagnose(recon_data, tree, git_data, truncated):
    findings = []

    def flag(kind, evidence):
        findings.append({"type": kind, "evidence": evidence})

    if not recon_data["manifests"]:
        flag("no_manifest", "No package manifest detected; language/ecosystem is unconfirmed.")

    if len(recon_data["manifests"]) > 1:
        flag("polyglot_or_monorepo",
             f"Multiple ecosystems present: {', '.join(recon_data['manifests'])}.")

    # ambiguous node package manager (more than one JS lockfile)
    js_locks = [pm for pm in recon_data["package_managers"] if pm in ("npm", "yarn", "pnpm", "bun")]
    if len(js_locks) > 1:
        flag("ambiguous_package_manager",
             f"Multiple JS lockfiles imply competing managers: {', '.join(js_locks)}.")

    if recon_data["test_file_count"] == 0:
        flag("no_tests", "No test files or test directories detected.")

    if not recon_data["ci"]:
        flag("no_ci", "No CI workflow detected (.github/workflows, .gitlab-ci.yml, ...).")

    if not recon_data["tooling"].get("docs"):
        flag("no_readme", "No README/CONTRIBUTING found at the paths scanned.")

    if not recon_data["tooling"].get("license"):
        flag("no_license", "No LICENSE file detected.")

    if not recon_data["entry_points"]:
        flag("no_entry_point", "Could not identify a main/index/app/server entry point.")

    if not git_data.get("available"):
        flag("git_conventions_unavailable",
             git_data.get("note", "Git conventions could not be read."))

    if truncated:
        flag("traversal_truncated",
             "File walk hit --max-files; tree and counts are partial.")

    return findings


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    args = parse_args()
    root = os.path.abspath(args.root)

    if not os.path.isdir(root):
        write({"error": f"--root is not a directory: {root}"}, args.out)
        return

    files, truncated = walk_repo(root, args.max_files)

    recon_data = recon(root, files)
    tree = directory_tree(root, args.max_depth)
    languages = language_breakdown(root, files)
    naming = naming_conventions(root, files)
    git_data = git_conventions(root, args.git_log)

    report = {
        "root": root,
        "file_count_scanned": len(files),
        "truncated": truncated,
        "reconnaissance": recon_data,
        "directory_tree": tree,
        "languages": languages,
        "conventions": {"naming": naming, "git": git_data},
        "findings": diagnose(recon_data, tree, git_data, truncated),
    }

    write(report, args.out)


def write(report, path):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"[collect_codebase_state] wrote {path}")
    print(f"[collect_codebase_state] findings: {len(report.get('findings', []))}")


if __name__ == "__main__":
    main()
