# wb Agent Guide

## Workspace Defaults

- Follow `/home/ryan/Documents/agent_context/CLI_TUI_STYLE_GUIDE.md` for CLI taste and help shape.
- Follow `/home/ryan/Documents/agent_context/CANONICAL_REFERENCE_IMPLEMENTATION_FOR_CLI_AND_TUI_APPS.md` for launcher, installer, and release behavior.

## Scope

- `wb` is a generic writing CLI for drafting long work one proposition at a time.
- Keep the app independent of any specific book, manuscript, author plan, or private project.
- Do not commit book outlines, manuscript drafts, proposition lists, or generated drafts to this repo.
- Book-specific data belongs in the user's book project as a separate JSON structure file and draft files.

## Config

- App config is XDG compliant: `$XDG_CONFIG_HOME/wb/config.json`, falling back to `~/.config/wb/config.json`.
- `wb conf` opens the app config.
- The app config may contain generic defaults and machine-local presets only:
  - `extension`
  - `min_chars`
  - `presets`
- A preset maps a user-facing name to a structure JSON path and drafts directory.
- Do not put book-specific planning content in the app repo or app config.

## Command Shape

- Keep the primary target explicit:
  - `wb <structure_json> <drafts_dir>`
  - `wb <structure_json> <drafts_dir> -1`
  - `wb <structure_json> <drafts_dir> status`
  - `wb <structure_json> <drafts_dir> ls`
  - `wb <structure_json> <drafts_dir> show`
  - `wb <structure_json> <drafts_dir> export -o manuscript.md`
- Preserve named presets:
  - `wb preset "an eye for an eye" <structure_json> <drafts_dir>`
  - `wb "an eye for an eye"`
  - `wb "an eye for an eye" status`
- No-arg `wb` prints help through the shared CLI contract.
