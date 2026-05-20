# wb

Writer's Block is a terminal-native drafting tool for writing long work one
proposition at a time.

The app is generic. It does not ship with any book plan, manuscript, or private
writing material.

By default, a proposition advances only after:

1. The draft body reaches the configured minimum character count.
2. The OpenAI quality gate scores that exact draft at least `7/10` against
   George Orwell's six rules.

## Install

```bash
./install.sh
```

Or install from GitHub:

```bash
curl -fsSL https://raw.githubusercontent.com/ryangerardwilson/wb/main/install.sh | bash
```

The installer keeps the internal runtime under `~/.wb/` and publishes the
user-facing command at `~/.local/bin/wb`.

If `~/.local/bin` is not already on your `PATH`, add it once to `~/.bashrc` and
reload:

```bash
export PATH="$HOME/.local/bin:$PATH"
source ~/.bashrc
```

## Usage

```bash
wb -h
wb -v
wb -u
```

Create a generic book config in the current directory:

```bash
wb init
```

Write the next proposition:

```bash
wb
wb w -1
```

Inspect progress:

```bash
wb st
wb sh
wb ls
```

Export completed draft bodies:

```bash
wb x -o manuscript.md
wb x -all
```

Use a specific book config:

```bash
wb w -c ./book.json
wb st -c ./book.json
wb x -o manuscript.md -c ./book.json
```

Edit the app config:

```bash
wb conf
```

## Config

App config is XDG compliant:

```text
$XDG_CONFIG_HOME/wb/config.json
~/.config/wb/config.json
```

The app config stores generic defaults only:

```json
{
  "book_config": "wb.json",
  "draft_dir": "drafts",
  "extension": "md",
  "min_chars": 500,
  "quality_gate": {
    "enabled": true,
    "provider": "openai",
    "model": "gpt-5.5",
    "threshold": 7,
    "rules": "orwell_6"
  }
}
```

Book-specific structure belongs in a separate book JSON file. That file defines
the title, chapters, propositions, and optional per-book settings. Drafts are
plain Markdown files next to that book config.

Editor resolution follows the workspace contract:

1. `$VISUAL`
2. `$EDITOR`
3. `vim`

The OpenAI API key is read by sourcing `~/.bashrc` and reading
`OPENAI_API_KEY`. The key is never written to the app repo or printed by `wb`.

To disable scoring for a specific book, set this in that book's JSON config:

```json
{
  "settings": {
    "quality_gate": {
      "enabled": false
    }
  }
}
```

## Release

This repo follows the workspace CLI contract:

```bash
./push_release_upgrade.sh
```

That script pushes the current branch, tags the next release, waits for the
GitHub release asset, and upgrades the installed app.
