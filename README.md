# PlanetScale Codex Plugin

Plugin for installing the [PlanetScale MCP server](https://planetscale.com/docs/connect/mcp), [PlanetScale Skills](https://github.com/planetscale/skills), and [Database Skills](https://db-skills.com/) into Codex.

## Prerequisites

- A plugin-capable Codex CLI or ChatGPT desktop app
- Git with submodule support when cloning the repository locally
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

This plugin pulls in skills from two upstream repositories via Git submodules:

| Upstream | Submodule path | What it provides |
| --- | --- | --- |
| [`planetscale/skills`](https://github.com/planetscale/skills) | `skills` | PlanetScale operating/assessment skills (safe orchestrator, inventory, Insights, Traffic Control, schema recommendations, and more) |
| [`planetscale/database-skills`](https://github.com/planetscale/database-skills) | `database-skills` | Engine skills for MySQL, Postgres, Vitess, and Neki |

Both track `main`. Codex loads `./skills/` by default and also loads `./database-skills/skills/` via the plugin manifest.

### Local bootstrap

Clone with submodules:

```bash
git clone --recurse-submodules https://github.com/planetscale/codex-plugin.git
```

If you already cloned without submodules:

```bash
git submodule update --init --recursive
```

### Manual one-off update

To pull the latest upstream skills into this repository:

```bash
git submodule sync --recursive
git submodule update --init --remote database-skills skills
```

Commit the resulting submodule pointer changes in this repository.

### Local testing

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
2. Confirm PlanetScale operating skills (for example `00-safe-orchestrator`) are available.
3. Confirm the MySQL, Postgres, Vitess, and Neki database skills are available.

### Automated weekly updates

GitHub Actions runs `.github/workflows/update-skills.yml` weekly and also supports manual runs (`workflow_dispatch`).

When either submodule has new commits, the workflow opens or updates a PR that contains only:

- The `database-skills` and/or `skills` submodule pointer updates
- `.gitmodules` (if submodule metadata changed)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for local setup, testing, and pull request requirements.

## License

This project is licensed under the [Apache License 2.0](LICENSE).
