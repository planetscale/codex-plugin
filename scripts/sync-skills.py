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
        "",
    ),
    (
        "database-skills",
        "https://github.com/planetscale/database-skills",
        "database_skills",
        "database",
        "",
        "database-",
    ),
)
VALID_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
INDEX_MARKERS = ("<!-- BEGIN GENERATED INDEX -->", "<!-- END GENERATED INDEX -->")
REFERENCE = re.compile(
    r"(?P<prefix>(?:\.\./)+)"
    r"(?P<target>[a-z0-9]+(?:-[a-z0-9]+)*)"
    r"(?P<suffix>(?:/[A-Za-z0-9._-]+)*/SKILL\.md)"
)


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
    source: Path,
    source_name: str,
    namespace: str,
    strip_prefix: str,
    name_prefix: str,
) -> tuple[list[tuple[str, Path, str, str]], dict[str, str]]:
    discovered: list[tuple[str, Path, str, str]] = []
    directory_names: dict[str, str] = {}
    for skill_md in sorted(source.rglob("SKILL.md")):
        fields = frontmatter(skill_md)
        original_name = fields.get("name", "")
        validate_name(original_name, skill_md)
        name = original_name.removeprefix(strip_prefix)
        name = name_prefix + name
        validate_name(name, skill_md)
        if name == namespace:
            raise ValueError(
                f"{skill_md} child name collides with namespace: {namespace}"
            )
        directory_name = skill_md.parent.name
        if directory_name in directory_names:
            raise ValueError(
                f"skill directory collision in {namespace}: {directory_name}"
            )
        directory_names[directory_name] = name
        discovered.append(
            (name, skill_md.parent, fields.get("description", ""), directory_name)
        )

    if not discovered:
        raise ValueError(f"{source_name} contains no SKILL.md files")
    return discovered, directory_names


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


def rewrite_references(
    path: Path,
    root: Path,
    namespace: str,
    directory_names: dict[str, dict[str, str]],
) -> int:
    text = path.read_text(encoding="utf-8")
    rewritten = 0

    def replace_path(match: re.Match[str]) -> str:
        nonlocal rewritten
        target = match.group("target")
        suffix = match.group("suffix")
        target_name = directory_names.get(namespace, {}).get(target)
        target_namespace = namespace
        if target_name is None:
            for candidate_namespace, names in directory_names.items():
                if target in names:
                    target_name = names[target]
                    target_namespace = candidate_namespace
                    break
        if target_name is None:
            return match.group(0)

        if target_namespace == namespace:
            replacement = f"{match.group('prefix')}{target_name}{suffix}"
        else:
            target_path = (
                root / "skills" / target_name / suffix.lstrip("/")
            )
            replacement = os.path.relpath(target_path, path.parent)
        if replacement != match.group(0):
            rewritten += 1
        return replacement

    text = REFERENCE.sub(replace_path, text)
    names = directory_names.get(namespace, {})
    if names and namespace == "planetscale":
        pattern = re.compile(
            r"(?<![A-Za-z0-9_-])(?:"
            + "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True))
            + r")(?![A-Za-z0-9_-])"
        )

        def replace_bare(match: re.Match[str]) -> str:
            nonlocal rewritten
            replacement = names[match.group(0)]
            if replacement != match.group(0):
                rewritten += 1
            return replacement

        text = pattern.sub(replace_bare, text)

    if rewritten:
        path.write_text(text, encoding="utf-8")
    return rewritten


def validate_references(root: Path) -> tuple[int, list[tuple[Path, str, Path]]]:
    reference_count = 0
    dangling: list[tuple[Path, str, Path]] = []
    for path in sorted(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for match in REFERENCE.finditer(text):
            link = match.group(0)
            target = (path.parent / link).resolve()
            reference_count += 1
            if not target.is_file():
                dangling.append((path, link, target))
    return reference_count, dangling


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
            f"| `{name}` | `skills/{name}/SKILL.md` | "
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
    destination.parent.mkdir(parents=True, exist_ok=True)
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
            tuple[
                str,
                str,
                str,
                str,
                Path,
                list[tuple[str, Path, str, str]],
                dict[str, str],
            ]
        ] = []
        all_names: dict[str, dict[str, str]] = {}
        flat_names: dict[str, str] = {}
        directory_names: dict[str, dict[str, str]] = {}
        index_names = {source[3] for source in SOURCES}

        for (
            repo_name,
            url,
            output_key,
            namespace,
            strip_prefix,
            name_prefix,
        ) in SOURCES:
            source = local_sources[repo_name]
            if source is None:
                source = clone_source(url, temp_root / repo_name)
            if not source.is_dir():
                raise ValueError(f"source does not exist: {source}")

            skills, source_directory_names = discover_skills(
                source, repo_name, namespace, strip_prefix, name_prefix
            )
            namespace_names = all_names.setdefault(namespace, {})
            namespace_directory_names = directory_names.setdefault(namespace, {})
            for name, _, _, directory_name in skills:
                if name in flat_names:
                    raise ValueError(
                        f"skill name collision: {name} in "
                        f"{flat_names[name]} and {repo_name}"
                    )
                if name in index_names:
                    raise ValueError(
                        f"skill name collides with index namespace: {name}"
                    )
                namespace_names[name] = repo_name
                flat_names[name] = repo_name
                if directory_name in namespace_directory_names:
                    raise ValueError(
                        f"skill directory collision in {namespace}: {directory_name}"
                    )
                namespace_directory_names[directory_name] = name
            assert source_directory_names == {
                directory_name: name
                for name, _, _, directory_name in skills
            }
            resolved.append(
                (
                    repo_name,
                    url,
                    output_key,
                    namespace,
                    source,
                    skills,
                    source_directory_names,
                )
            )

        shutil.rmtree(destination, ignore_errors=True)
        destination.mkdir(parents=True)
        third_party = root / "third_party"
        third_party.mkdir(exist_ok=True)

        provenance: list[dict[str, object]] = []
        outputs: dict[str, str] = {}
        index_children: dict[str, list[tuple[str, str]]] = {}
        for (
            repo_name,
            url,
            output_key,
            namespace,
            source,
            skills,
            _,
        ) in resolved:
            for name, skill_dir, description, _ in skills:
                child_destination = destination / name
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
                    "skills": [name for name, _, _, _ in skills],
                }
            )
            before = old_sources.get(repo_name, {}).get("sha", "")
            outputs[f"{output_key}_before_sha"] = before
            outputs[f"{output_key}_after_sha"] = sha
            outputs[f"{output_key}_compare_url"] = (
                f"{url}/compare/{before or 'unknown'}...{sha}"
            )

        rewritten_references = 0
        skill_namespaces = {
            name: namespace
            for namespace, names in directory_names.items()
            for name in names.values()
        }
        for path in sorted(destination.rglob("*.md")):
            name = path.relative_to(destination).parts[0]
            namespace = skill_namespaces.get(name)
            if namespace is not None:
                rewritten_references += rewrite_references(
                    path, root, namespace, directory_names
                )
        reference_count, dangling = validate_references(destination)
        if dangling:
            details = "; ".join(
                f"{path}: {link} -> {target}" for path, link, target in dangling
            )
            raise ValueError(f"dangling vendored skill references: {details}")
        outputs["rewritten_references"] = str(rewritten_references)
        outputs["vendored_skill_references"] = str(reference_count)
        outputs["dangling_references"] = "0"

        for namespace, children in index_children.items():
            render_index(root, namespace, children)

        provenance_path.write_text(
            json.dumps({"sources": provenance}, indent=2) + "\n",
            encoding="utf-8",
        )
        write_outputs(outputs)


if __name__ == "__main__":
    main()
