# wb Agent Guide

## Workspace Defaults

- Follow `/home/ryan/Documents/agent_context/CLI_TUI_STYLE_GUIDE.md` for CLI taste and help shape.
- Follow `/home/ryan/Documents/agent_context/CANONICAL_REFERENCE_IMPLEMENTATION_FOR_CLI_AND_TUI_APPS.md` for launcher, installer, and release behavior.

## Scope

- `wb` is a generic writing CLI for drafting long work one proposition at a time.
- Keep the app independent of any specific book, manuscript, author plan, or private project.
- Do not commit book outlines, manuscript drafts, proposition lists, or generated drafts to this repo.
- Book-specific data belongs in the user's book project as a separate JSON config and draft files.

## Config

- App config is XDG compliant: `$XDG_CONFIG_HOME/wb/config.json`, falling back to `~/.config/wb/config.json`.
- `wb conf` opens the app config.
- The app config may contain generic defaults only, such as the default book config filename, draft directory, extension, minimum character threshold, and generic quality-gate settings.
- Do not put book-specific planning in the XDG app config unless the user explicitly asks for a machine-local personal setup.
- The default quality gate uses OpenAI `gpt-5.5` to score draft bodies against George Orwell's six prose rules.
- If the quality gate fails in an interactive terminal, `wb` may ask whether to use OpenAI to rewrite the draft in Orwell's plain style, then reopen the draft in the editor for human edits.
- The OpenAI API key must be read by sourcing `~/.bashrc` and reading `OPENAI_API_KEY`; never commit, print, or log plaintext key material.

## Command Shape

- Keep the primary loop compact:
  - `wb`
  - `wb w -1`
  - `wb st`
  - `wb sh`
  - `wb ls`
  - `wb x -o manuscript.md`
  - `wb init`
  - `wb conf`
- Use `-c <book_json>` for an explicit book config path.
- Preserve the no-arg primary action: `wb` opens the next proposition.
