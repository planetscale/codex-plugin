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
    r"(?P<suffix>(?:/[A-Za-z0-9._-]+)+)"
)
MARKDOWN_LINK = re.compile(
    r"\]\((?P<link>(?!(?:[A-Za-z][A-Za-z0-9+.-]*:|//|#))[^)\s]+)"
)
UPSTREAM_URL = re.compile(
    r"https://raw.githubusercontent.com/planetscale/"
    r"(?P<repo>skills|database-skills)/main/"
    r"(?P<path>[^\s)\]}>\"']+)"
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
    generated_root: Path,
    namespace: str,
    directory_names: dict[str, dict[str, str]],
) -> tuple[int, int, int]:
    text = path.read_text(encoding="utf-8")
    rewritten = 0
    rewritten_upstream_urls = 0
    unresolved_upstream_urls = 0

    def replace_upstream_url(match: re.Match[str]) -> str:
        nonlocal rewritten_upstream_urls, unresolved_upstream_urls
        repo = match.group("repo")
        upstream_path = match.group("path")
        if repo == "database-skills":
            prefix = "skills/"
            target_namespace = "database"
            if not upstream_path.startswith(prefix):
                unresolved_upstream_urls += 1
                return match.group(0)
            upstream_path = upstream_path[len(prefix) :]
        else:
            target_namespace = "planetscale"

        parts = upstream_path.split("/", 1)
        target_name = directory_names.get(target_namespace, {}).get(parts[0])
        if target_name is None:
            unresolved_upstream_urls += 1
            return match.group(0)
        relative_path = parts[1] if len(parts) == 2 else ""
        target = generated_root / "skills" / target_name / relative_path
        if not target.is_file():
            unresolved_upstream_urls += 1
            return match.group(0)
        rewritten_upstream_urls += 1
        return os.path.relpath(target, path.parent)

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
                generated_root / "skills" / target_name / suffix.lstrip("/")
            )
            replacement = os.path.relpath(target_path, path.parent)
        if replacement != match.group(0):
            rewritten += 1
        return replacement

    text = UPSTREAM_URL.sub(replace_upstream_url, text)
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
    elif rewritten_upstream_urls:
        path.write_text(text, encoding="utf-8")
    return rewritten, rewritten_upstream_urls, unresolved_upstream_urls


def validate_references(root: Path) -> tuple[int, list[tuple[Path, str, Path]]]:
    reference_count = 0
    dangling: list[tuple[Path, str, Path]] = []
    for path in sorted(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        links: dict[int, str] = {
            match.start(): match.group(0) for match in REFERENCE.finditer(text)
        }
        links.update(
            {
                match.start("link"): match.group("link")
                for match in MARKDOWN_LINK.finditer(text)
            }
        )
        for link in links.values():
            target_link = re.split(r"[#?]", link, maxsplit=1)[0]
            target = (path.parent / target_link).resolve()
            reference_count += 1
            if not target.is_file():
                dangling.append((path, link, target))
    return reference_count, dangling


def install_staged_tree(
    staged_skills: Path,
    staged_third_party: Path,
    staged_provenance: Path,
    destination: Path,
    third_party: Path,
    provenance_path: Path,
    backup_root: Path,
) -> None:
    replacements = (
        (staged_skills, destination, backup_root / "skills"),
        (staged_third_party, third_party, backup_root / "third_party"),
        (staged_provenance, provenance_path, backup_root / "skill-sources.json"),
    )
    installed: list[tuple[Path, Path]] = []
    backups: list[tuple[Path, Path]] = []
    try:
        for staged, target, backup in replacements:
            if target.exists():
                backup.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, backup)
                backups.append((backup, target))
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged, target)
            installed.append((target, staged))
    except Exception:
        for target, _ in reversed(installed):
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
        for backup, target in reversed(backups):
            os.replace(backup, target)
        raise


def first_sentence(description: str) -> str:
    match = re.search(r"[.!?](?:\s|$)", description)
    if match:
        return description[: match.start() + 1]
    return description


def render_index(
    template_root: Path,
    output_root: Path,
    namespace: str,
    children: list[tuple[str, str]],
) -> None:
    template = template_root / "skill-index" / namespace / "SKILL.md"
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
    destination = output_root / "skills" / namespace / "SKILL.md"
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
    third_party = root / "third_party"
    provenance_path = root / "skill-sources.json"
    old_sources = previous_sources(provenance_path)
    local_sources = {
        "skills": args.skills_source.resolve() if args.skills_source else None,
        "database-skills": (
            args.database_skills_source.resolve()
            if args.database_skills_source
            else None
        ),
    }

    with tempfile.TemporaryDirectory(
        prefix="planet-scale-skills-", dir=root.parent
    ) as temp_dir:
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

        staged_root = temp_root / "staged"
        staged_destination = staged_root / "skills"
        staged_third_party = staged_root / "third_party"
        staged_destination.mkdir(parents=True)
        if third_party.is_dir():
            shutil.copytree(third_party, staged_third_party)
        else:
            staged_third_party.mkdir(parents=True)

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
                child_destination = staged_destination / name
                shutil.copytree(skill_dir, child_destination)
                rewrite_name(child_destination / "SKILL.md", name)
                index_children.setdefault(namespace, []).append((name, description))

            license_source = source / "LICENSE"
            license_destination = staged_third_party / repo_name
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
        rewritten_upstream_urls = 0
        unresolved_upstream_urls = 0
        skill_namespaces = {
            name: namespace
            for namespace, names in directory_names.items()
            for name in names.values()
        }
        for path in sorted(staged_destination.rglob("*.md")):
            name = path.relative_to(staged_destination).parts[0]
            namespace = skill_namespaces.get(name)
            if namespace is not None:
                (
                    path_references,
                    path_upstream_urls,
                    path_unresolved_urls,
                ) = rewrite_references(
                    path, staged_root, namespace, directory_names
                )
                rewritten_references += path_references
                rewritten_upstream_urls += path_upstream_urls
                unresolved_upstream_urls += path_unresolved_urls
        for namespace, children in index_children.items():
            render_index(root, staged_root, namespace, children)
        reference_count, dangling = validate_references(staged_destination)
        if dangling:
            details = "; ".join(
                f"{path}: {link} -> {target}" for path, link, target in dangling
            )
            raise ValueError(f"dangling vendored skill references: {details}")
        outputs["rewritten_references"] = str(rewritten_references)
        outputs["vendored_skill_references"] = str(reference_count)
        outputs["dangling_references"] = "0"
        outputs["rewritten_upstream_urls"] = str(rewritten_upstream_urls)
        outputs["unresolved_upstream_urls"] = str(unresolved_upstream_urls)

        staged_provenance = staged_root / "skill-sources.json"
        staged_provenance.write_text(
            json.dumps({"sources": provenance}, indent=2) + "\n",
            encoding="utf-8",
        )
        write_outputs(outputs)
        install_staged_tree(
            staged_destination,
            staged_third_party,
            staged_provenance,
            destination,
            third_party,
            provenance_path,
            temp_root / "backup",
        )


if __name__ == "__main__":
    main()
