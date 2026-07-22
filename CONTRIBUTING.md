# Contributing

Thanks for contributing to the PlanetScale Codex plugin.

## Choose the correct repository

This repository packages the PlanetScale MCP server configuration and two skill collections. Submit changes where their source lives:

- Plugin manifest, marketplace metadata, MCP configuration, release automation, and packaging changes belong in this repository.
- PlanetScale operating skill changes belong in [`planetscale/skills`](https://github.com/planetscale/skills).
- MySQL, Postgres, Vitess, and Neki database skill changes belong in [`planetscale/database-skills`](https://github.com/planetscale/database-skills).

Changes to either skill collection reach this repository as reviewed submodule pointer updates.

## Prerequisites

- Git with submodule support
- A plugin-capable Codex CLI or ChatGPT desktop app
- A PlanetScale account for testing authenticated MCP operations

## Set up a local checkout

```bash
git clone --recurse-submodules https://github.com/planetscale/codex-plugin.git
cd codex-plugin
```

If the repository is already cloned, initialize its submodules:

```bash
git submodule update --init --recursive
```

## Test a change

Add the working copy as a local marketplace and install the plugin:

```bash
codex plugin marketplace add /absolute/path/to/codex-plugin
```

Then restart Codex or the ChatGPT desktop app and verify:

1. The `PlanetScale` MCP server is listed.
2. PlanetScale operating skills are available.
3. The MySQL, Postgres, Vitess, and Neki database skills are available.
4. Authentication succeeds with `codex mcp login PlanetScale` when the change requires MCP access.

## Pull requests

- Keep commits focused and sign them.
- Do not commit credentials, tokens, customer data, or local configuration.
- Pin GitHub Actions to a full-length commit SHA and retain a version comment such as `# v4`.
- Describe the change, its user impact, and the validation performed.
- Obtain at least one approval, including review from a Code Owner.
