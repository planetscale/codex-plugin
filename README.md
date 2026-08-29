# PlanetScale Codex Plugin

Plugin for installing the [PlanetScale MCP server](https://planetscale.com/docs/connect/mcp), [PlanetScale Skills](https://github.com/planetscale/skills), and [Database Skills](https://db-skills.com/) into Codex.

## Prerequisites

- A plugin-capable Codex CLI or ChatGPT desktop app
- A PlanetScale account for authenticated MCP operations

## Install from GitHub

Add this repository as a marketplace, then install the plugin:

```bash
codex plugin marketplace add planetscale/codex-plugin
```

Or in the ChatGPT desktop app (Work mode or Codex), open Plugins, add the marketplace source, and install **PlanetScale**.

### Verify it loaded

In the Codex TUI, run `/mcp` to see the `PlanetScale` MCP server.

If it does not appear immediately after install, restart Codex and check `/mcp` again. Plugin-provided MCP server changes are applied on restart. Authenticate with:

```bash
codex mcp login PlanetScale
```

## Skills Source and Sync

This plugin vendors skills from two upstream repositories:

| Upstream | Vendored path | What it provides |
| --- | --- | --- |
| [`planetscale/skills`](https://github.com/planetscale/skills) | `skills/` | PlanetScale operating/assessment skills |
| [`planetscale/database-skills`](https://github.com/planetscale/database-skills) | `skills/` | Engine skills for MySQL, Postgres, Vitess, and Neki |

Both track `main`. The sync script copies each upstream skill directory directly under `skills/`, using the frontmatter `name` as the directory name after stripping the `planetscale-` prefix from operating skills and adding the `database-` prefix to engine skills. It skips upstream directories without a `SKILL.md` and records source commit SHAs, namespaces, and vendored names in `.codex-plugin/skill-sources.json`.

Each namespace has an index skill at `skills/database/SKILL.md` or `skills/planetscale/SKILL.md`. The index tables link to every child skill and are generated from the child frontmatter descriptions. Their source prose and generated-region markers live in `skill-index/`; edit those templates rather than the rendered indexes.

The 19 source skills are direct siblings under `skills/` so both legacy and direct-child skill discovery can load them. Operating skills use names such as `safe-orchestrator`, while engine skills use the `database-` prefix, such as `database-mysql`.

### Local sync and testing

Clone the repository normally:

```bash
git clone https://github.com/planetscale/codex-plugin.git
```

Refresh vendored skills from upstream:

```bash
python3 scripts/sync-skills.py
```

Add a personal or repo marketplace that points at this working copy, then install the plugin and restart the ChatGPT desktop app or Codex CLI.

Example personal marketplace entry (`~/.agents/plugins/marketplace.json`):

```json
{
  "name": "local-planetscale",
  "interface": {
    "displayName": "Local PlanetScale"
  },
  "plugins": [
    {
      "name": "planetscale",
      "source": {
        "source": "local",
        "path": "./"
      },
      "policy": {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL"
      },
      "category": "Developer Tools"
    }
  ]
}
```

When testing from a personal marketplace, copy or symlink this plugin directory under the marketplace root (for example `~/.codex/plugins/planetscale`) and set `source.path` accordingly, or run:

```bash
codex plugin marketplace add /absolute/path/to/codex-plugin
```

1. Confirm the `PlanetScale` MCP server is listed (authentication required on first use).
2. Confirm PlanetScale operating skills (for example `safe-orchestrator`) are available.
3. Confirm the `database-mysql`, `database-postgres`, `database-vitess`, and `database-neki` skills are available.

### Automated weekly updates

GitHub Actions runs `.github/workflows/update-skills.yml` weekly and also supports manual runs (`workflow_dispatch`).

It runs `scripts/sync-skills.py`, validates the vendored layout, and opens a PR when the vendored skills, third-party licenses, or provenance file change. The PR body includes compare links to the upstream commits.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for local setup, testing, and pull request requirements.

## License

This project is licensed under the [Apache License 2.0](LICENSE).
