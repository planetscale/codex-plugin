#!/usr/bin/env python3
"""Vendor skills from the PlanetScale upstream repositories."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


SOURCES = (
    (
        "skills",
        "https://github.com/planetscale/skills",
        "skills",
        "planetscale",
        "planetscale-",
    ),
    (
        "database-skills",
        "https://github.com/planetscale/database-skills",
        "database_skills",
        "database",
        "",
    ),
)
VALID_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
INDEX_MARKERS = ("<!-- BEGIN GENERATED INDEX -->", "<!-- END GENERATED INDEX -->")


def git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return result.stdout.strip()


def clone_source(url: str, destination: Path) -> Path:
    git(
        "clone",
        "--depth",
        "1",
        "--branch",
        "main",
        "--single-branch",
        url,
        str(destination),
    )
    return destination


def frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{path} has no frontmatter")

    fields: dict[str, str] = {}
    index = 1
    while index < len(lines):
        line = lines[index]
        if line.strip() == "---":
            break
        key, separator, value = line.partition(":")
        if separator and key.strip() in {"name", "description"}:
            value = value.strip().strip("\"'")
            if value in {">", ">-", ">+", "|", "|-", "|+"}:
                index += 1
                continuation = []
                while index < len(lines) and (
                    lines[index].startswith(" ") or lines[index].startswith("\t")
                ):
                    continuation.append(lines[index].strip())
                    index += 1
                value = " ".join(continuation)
            else:
                index += 1
            fields[key.strip()] = value
            continue
        index += 1
    return fields


def validate_name(name: str, path: Path) -> None:
    if not name:
        raise ValueError(f"{path} is missing frontmatter name")
    if len(name) > 64:
        raise ValueError(f"{path} has a name longer than 64 characters: {name}")
    if not VALID_NAME.fullmatch(name):
        raise ValueError(f"{path} has an invalid frontmatter name: {name}")


def discover_skills(
    source: Path, source_name: str, namespace: str, prefix: str
) -> list[tuple[str, Path, str]]:
    discovered: list[tuple[str, Path, str]] = []
    for skill_md in sorted(source.rglob("SKILL.md")):
        fields = frontmatter(skill_md)
        original_name = fields.get("name", "")
        validate_name(original_name, skill_md)
        name = original_name.removeprefix(prefix)
        validate_name(name, skill_md)
        if name == namespace:
            raise ValueError(
                f"{skill_md} child name collides with namespace: {namespace}"
            )
        discovered.append((name, skill_md.parent, fields.get("description", "")))

    if not discovered:
        raise ValueError(f"{source_name} contains no SKILL.md files")
    return discovered


def previous_sources(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {item["repo"]: item for item in data.get("sources", [])}


def rewrite_name(path: Path, name: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{path} has no frontmatter")

    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            break
        if line.startswith("name:"):
            newline = "\n" if line.endswith("\n") else ""
            lines[index] = f"name: {name}{newline}"
            path.write_text("".join(lines), encoding="utf-8")
            return
    raise ValueError(f"{path} is missing frontmatter name")


def first_sentence(description: str) -> str:
    match = re.search(r"[.!?](?:\s|$)", description)
    if match:
        return description[: match.start() + 1]
    return description


def render_index(root: Path, namespace: str, children: list[tuple[str, str]]) -> None:
    template = root / "skill-index" / namespace / "SKILL.md"
    if not template.is_file():
        raise ValueError(f"missing index template: {template}")

    text = template.read_text(encoding="utf-8")
    begin, end = INDEX_MARKERS
    begin_index = text.find(begin)
    end_index = text.find(end)
    if begin_index < 0 or end_index < 0 or end_index < begin_index:
        raise ValueError(f"index template has invalid markers: {template}")

    rows = [
        "| Skill | Path | Description |",
        "| --- | --- | --- |",
    ]
    for name, description in sorted(children):
        escaped_description = first_sentence(description).replace("|", "\\|")
        rows.append(
            f"| `{name}` | `skills/{namespace}/{name}/SKILL.md` | "
            f"{escaped_description} |"
        )
    generated = "\n".join(rows)
    rendered = (
        text[: begin_index + len(begin)]
        + "\n"
        + generated
        + "\n"
        + text[end_index:]
    )
    destination = root / "skills" / namespace / "SKILL.md"
    destination.write_text(rendered, encoding="utf-8")


def write_outputs(outputs: dict[str, str]) -> None:
    for key, value in outputs.items():
        print(f"{key}={value}")
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as output:
            for key, value in outputs.items():
                output.write(f"{key}={value}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skills-source", type=Path)
    parser.add_argument("--database-skills-source", type=Path)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    destination = root / "skills"
    provenance_path = root / ".codex-plugin" / "skill-sources.json"
    old_sources = previous_sources(provenance_path)
    local_sources = {
        "skills": args.skills_source.resolve() if args.skills_source else None,
        "database-skills": (
            args.database_skills_source.resolve()
            if args.database_skills_source
            else None
        ),
    }

    with tempfile.TemporaryDirectory(prefix="planet-scale-skills-") as temp_dir:
        temp_root = Path(temp_dir)
        resolved: list[
            tuple[str, str, str, str, Path, list[tuple[str, Path, str]]]
        ] = []
        all_names: dict[str, dict[str, str]] = {}

        for repo_name, url, output_key, namespace, prefix in SOURCES:
            source = local_sources[repo_name]
            if source is None:
                source = clone_source(url, temp_root / repo_name)
            if not source.is_dir():
                raise ValueError(f"source does not exist: {source}")

            skills = discover_skills(source, repo_name, namespace, prefix)
            namespace_names = all_names.setdefault(namespace, {})
            for name, _, _ in skills:
                if name in namespace_names:
                    raise ValueError(
                        f"skill name collision in {namespace}: {name} in "
                        f"{namespace_names[name]} and {repo_name}"
                    )
                namespace_names[name] = repo_name
            resolved.append((repo_name, url, output_key, namespace, source, skills))

        shutil.rmtree(destination, ignore_errors=True)
        destination.mkdir(parents=True)
        third_party = root / "third_party"
        third_party.mkdir(exist_ok=True)

        provenance: list[dict[str, object]] = []
        outputs: dict[str, str] = {}
        index_children: dict[str, list[tuple[str, str]]] = {}
        for repo_name, url, output_key, namespace, source, skills in resolved:
            namespace_destination = destination / namespace
            namespace_destination.mkdir(parents=True, exist_ok=True)
            for name, skill_dir, description in skills:
                child_destination = namespace_destination / name
                shutil.copytree(skill_dir, child_destination)
                rewrite_name(child_destination / "SKILL.md", name)
                index_children.setdefault(namespace, []).append((name, description))

            license_source = source / "LICENSE"
            license_destination = third_party / repo_name
            shutil.rmtree(license_destination, ignore_errors=True)
            if license_source.is_file():
                license_destination.mkdir(parents=True, exist_ok=True)
                shutil.copy2(license_source, license_destination / "LICENSE")

            sha = git("-C", str(source), "rev-parse", "HEAD")
            provenance.append(
                {
                    "repo": repo_name,
                    "url": url,
                    "sha": sha,
                    "namespace": namespace,
                    "skills": [name for name, _, _ in skills],
                }
            )
            before = old_sources.get(repo_name, {}).get("sha", "")
            outputs[f"{output_key}_before_sha"] = before
            outputs[f"{output_key}_after_sha"] = sha
            outputs[f"{output_key}_compare_url"] = (
                f"{url}/compare/{before or 'unknown'}...{sha}"
            )

        for namespace, children in index_children.items():
            render_index(root, namespace, children)

        provenance_path.write_text(
            json.dumps({"sources": provenance}, indent=2) + "\n",
            encoding="utf-8",
        )
        write_outputs(outputs)


if __name__ == "__main__":
    main()
