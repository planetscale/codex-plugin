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
    ("skills", "https://github.com/planetscale/skills", "skills"),
    ("database-skills", "https://github.com/planetscale/database-skills", "database_skills"),
)
VALID_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


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
    git("clone", "--depth", "1", "--branch", "main", "--single-branch", url, str(destination))
    return destination


def frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{path} has no frontmatter")

    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, separator, value = line.partition(":")
        if separator and key.strip() in {"name", "description"}:
            fields[key.strip()] = value.strip().strip("\"'")
    return fields


def discover_skills(source: Path, source_name: str) -> list[tuple[str, Path]]:
    discovered: list[tuple[str, Path]] = []
    for skill_md in sorted(source.rglob("SKILL.md")):
        fields = frontmatter(skill_md)
        name = fields.get("name", "")
        if not name:
            raise ValueError(f"{skill_md} is missing frontmatter name")
        if len(name) > 64:
            raise ValueError(f"{skill_md} has a name longer than 64 characters: {name}")
        if not VALID_NAME.fullmatch(name):
            raise ValueError(f"{skill_md} has an invalid frontmatter name: {name}")
        discovered.append((name, skill_md.parent))

    if not discovered:
        raise ValueError(f"{source_name} contains no SKILL.md files")
    return discovered


def previous_sources(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {item["repo"]: item for item in data.get("sources", [])}


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
        resolved: list[tuple[str, str, str, Path, list[tuple[str, Path]]]] = []
        all_names: dict[str, str] = {}

        for repo_name, url, output_key in SOURCES:
            source = local_sources[repo_name]
            if source is None:
                source = clone_source(url, temp_root / repo_name)
            if not source.is_dir():
                raise ValueError(f"source does not exist: {source}")

            skills = discover_skills(source, repo_name)
            for name, _ in skills:
                if name in all_names:
                    raise ValueError(
                        f"skill name collision: {name} in {all_names[name]} and {repo_name}"
                    )
                all_names[name] = repo_name
            resolved.append((repo_name, url, output_key, source, skills))

        shutil.rmtree(destination, ignore_errors=True)
        destination.mkdir(parents=True)
        third_party = root / "third_party"
        third_party.mkdir(exist_ok=True)

        provenance: list[dict[str, object]] = []
        outputs: dict[str, str] = {}
        for repo_name, url, output_key, source, skills in resolved:
            for name, skill_dir in skills:
                shutil.copytree(skill_dir, destination / name)

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
                    "skills": [name for name, _ in skills],
                }
            )
            before = old_sources.get(repo_name, {}).get("sha", "")
            outputs[f"{output_key}_before_sha"] = before
            outputs[f"{output_key}_after_sha"] = sha
            outputs[f"{output_key}_compare_url"] = (
                f"{url}/compare/{before or 'unknown'}...{sha}"
            )

        provenance_path.write_text(
            json.dumps({"sources": provenance}, indent=2) + "\n",
            encoding="utf-8",
        )
        write_outputs(outputs)


if __name__ == "__main__":
    main()
