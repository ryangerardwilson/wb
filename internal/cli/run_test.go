package cli

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

type commandResult struct {
	code int
	out  string
	err  string
}

func runCommand(t *testing.T, cwd string, env map[string]string, args ...string) commandResult {
	t.Helper()
	return runCommandWithInput(t, cwd, env, "", args...)
}

func runCommandWithInput(t *testing.T, cwd string, env map[string]string, input string, args ...string) commandResult {
	t.Helper()
	oldWd, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Chdir(cwd); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := os.Chdir(oldWd); err != nil {
			t.Fatal(err)
		}
	})
	for key, value := range env {
		t.Setenv(key, value)
	}

	var out bytes.Buffer
	var errOut bytes.Buffer
	runner := NewRunner(&out, &errOut)
	if input != "" {
		runner.In = strings.NewReader(input)
	}
	code := runner.Run(args)
	return commandResult{code: code, out: out.String(), err: errOut.String()}
}

func writeStructure(t *testing.T, path string, minChars int, propositionCount int) {
	t.Helper()
	propositions := make([]string, 0, propositionCount)
	for index := 1; index <= propositionCount; index++ {
		propositions = append(propositions, "Argue thing "+string(rune('0'+index))+".")
	}
	data := map[string]any{
		"title": "Small",
		"settings": map[string]any{
			"min_chars": minChars,
			"extension": "md",
		},
		"chapters": []any{
			map[string]any{
				"title":        "One",
				"propositions": propositions,
			},
		},
	}
	encoded, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, append(encoded, '\n'), 0o644); err != nil {
		t.Fatal(err)
	}
}

func TestHelpVersionAndNoArgContract(t *testing.T) {
	tmp := t.TempDir()
	env := map[string]string{"XDG_CONFIG_HOME": filepath.Join(tmp, "config")}

	bare := runCommand(t, tmp, env)
	help := runCommand(t, tmp, env, "help")
	version := runCommand(t, tmp, env, "version")

	if bare.code != 0 || help.code != 0 || version.code != 0 {
		t.Fatalf("unexpected codes: bare=%d help=%d version=%d", bare.code, help.code, version.code)
	}
	if bare.out != help.out {
		t.Fatalf("bare output did not match help\nbare:\n%s\nhelp:\n%s", bare.out, help.out)
	}
	for _, needle := range []string{
		"WriteNow",
		"global actions:",
		"features:",
		"writenow list",
		"writenow start 1",
		"writenow tui",
		"writenow upgrade",
	} {
		if !strings.Contains(help.out, needle) {
			t.Fatalf("help missing %q\n%s", needle, help.out)
		}
	}
	for _, needle := range []string{"usage:", "--help", `writenow "an eye for an eye"`, `writenow use`, "wb "} {
		if strings.Contains(help.out, needle) {
			t.Fatalf("help should not contain %q\n%s", needle, help.out)
		}
	}
	if version.out != "0.0.0\n" {
		t.Fatalf("unexpected version output: %q", version.out)
	}
}

func TestConfigCreatesXDGAppConfig(t *testing.T) {
	tmp := t.TempDir()
	xdg := filepath.Join(tmp, "xdg")
	env := map[string]string{"XDG_CONFIG_HOME": xdg, "EDITOR": "true", "VISUAL": ""}

	result := runCommand(t, tmp, env, "config")
	configPath := filepath.Join(xdg, "writenow", "config.json")

	if result.code != 0 {
		t.Fatalf("config failed: code=%d err=%s", result.code, result.err)
	}
	if _, err := os.Stat(configPath); err != nil {
		t.Fatalf("config was not created: %v", err)
	}
	data, err := os.ReadFile(configPath)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(data), `"presets": {}`) {
		t.Fatalf("unexpected config:\n%s", data)
	}
}

func TestInitPresetAndStatusUseExplicitPaths(t *testing.T) {
	tmp := t.TempDir()
	env := map[string]string{"XDG_CONFIG_HOME": filepath.Join(tmp, "xdg")}

	initResult := runCommand(t, tmp, env, "init", "structure.json")
	presetResult := runCommand(t, tmp, env, "preset", "save", "small", "structure", "structure.json", "drafts", "drafts")
	listResult := runCommand(t, tmp, env, "list")

	if initResult.code != 0 || presetResult.code != 0 || listResult.code != 0 {
		t.Fatalf("codes init=%d preset=%d list=%d\nstderr=%s", initResult.code, presetResult.code, listResult.code, listResult.err)
	}
	for _, needle := range []string{
		"writenow books",
		"1. small",
		"title    : Untitled Book",
		"structure: structure.json",
		"drafts   : drafts",
		"progress : 0/1 (0%)",
	} {
		if !strings.Contains(listResult.out, needle) {
			t.Fatalf("list missing %q\n%s", needle, listResult.out)
		}
	}
}

func TestListReportsSavedProjectsFromXDGConfig(t *testing.T) {
	tmp := t.TempDir()
	xdg := filepath.Join(tmp, "xdg")
	structure := filepath.Join(tmp, "structure.json")
	drafts := filepath.Join(tmp, "drafts")
	writeStructure(t, structure, 5, 2)
	env := map[string]string{"XDG_CONFIG_HOME": xdg}

	preset := runCommand(t, tmp, env, "preset", "save", "small", "structure", structure, "drafts", drafts)
	draftPath := filepath.Join(drafts, "00-one", "01.md")
	writeCompletedDraft(t, draftPath, "<!-- writenow:draft:start -->\nfirst body")
	list := runCommand(t, tmp, env, "list")

	if preset.code != 0 || list.code != 0 {
		t.Fatalf("codes preset=%d list=%d err=%s", preset.code, list.code, list.err)
	}
	for _, needle := range []string{
		"writenow books",
		"1. small",
		"title    : Small",
		"progress : 1/2 (50%)",
		"next     : One / 2",
		"chars    : 0/5",
		"structure: structure.json",
		"drafts   : drafts",
	} {
		if !strings.Contains(list.out, needle) {
			t.Fatalf("list missing %q\n%s", needle, list.out)
		}
	}
}

func TestStartByBookNumberOpensSavedBook(t *testing.T) {
	tmp := t.TempDir()
	xdg := filepath.Join(tmp, "xdg")
	structure := filepath.Join(tmp, "structure.json")
	drafts := filepath.Join(tmp, "drafts")
	writeStructure(t, structure, 1, 1)
	editor := filepath.Join(tmp, "editor.sh")
	if err := os.WriteFile(editor, []byte("#!/usr/bin/env bash\nprintf 'x' >> \"$1\"\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	env := map[string]string{
		"XDG_CONFIG_HOME": xdg,
		"EDITOR":          editor,
		"VISUAL":          "",
	}

	preset := runCommand(t, tmp, env, "preset", "save", "small", "structure", structure, "drafts", drafts)
	start := runCommand(t, tmp, env, "start", "1")

	if preset.code != 0 || start.code != 0 {
		t.Fatalf("codes preset=%d start=%d out=%s err=%s", preset.code, start.code, start.out, start.err)
	}
	if !strings.Contains(start.out, "start 1: small") || !strings.Contains(start.out, "done 1/1") {
		t.Fatalf("unexpected start output:\n%s", start.out)
	}
	if _, err := os.Stat(filepath.Join(drafts, "00-one", "01.md")); err != nil {
		t.Fatalf("draft was not created: %v", err)
	}
}

func TestStartPromptsForBookNumberWhenOmitted(t *testing.T) {
	tmp := t.TempDir()
	xdg := filepath.Join(tmp, "xdg")
	structure := filepath.Join(tmp, "structure.json")
	drafts := filepath.Join(tmp, "drafts")
	writeStructure(t, structure, 1, 1)
	editor := filepath.Join(tmp, "editor.sh")
	if err := os.WriteFile(editor, []byte("#!/usr/bin/env bash\nprintf 'x' >> \"$1\"\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	env := map[string]string{
		"XDG_CONFIG_HOME": xdg,
		"EDITOR":          editor,
		"VISUAL":          "",
	}

	preset := runCommand(t, tmp, env, "preset", "save", "small", "structure", structure, "drafts", drafts)
	start := runCommandWithInput(t, tmp, env, "1\n", "start")

	if preset.code != 0 || start.code != 0 {
		t.Fatalf("codes preset=%d start=%d out=%s err=%s", preset.code, start.code, start.out, start.err)
	}
	for _, needle := range []string{"writenow books", "1. small", "book number: ", "done 1/1"} {
		if !strings.Contains(start.out, needle) {
			t.Fatalf("start prompt missing %q\n%s", needle, start.out)
		}
	}
}

func TestTUIRequiresInteractiveTerminal(t *testing.T) {
	tmp := t.TempDir()
	xdg := filepath.Join(tmp, "xdg")
	structure := filepath.Join(tmp, "structure.json")
	drafts := filepath.Join(tmp, "drafts")
	writeStructure(t, structure, 5, 2)
	env := map[string]string{"XDG_CONFIG_HOME": xdg}

	preset := runCommand(t, tmp, env, "preset", "save", "small", "structure", structure, "drafts", drafts)
	tui := runCommand(t, tmp, env, "tui")

	if preset.code != 0 {
		t.Fatalf("preset failed: %s", preset.err)
	}
	if tui.code != 1 {
		t.Fatalf("expected tui failure in non-tty, got code=%d out=%s err=%s", tui.code, tui.out, tui.err)
	}
	if !strings.Contains(tui.err, "interactive terminal") {
		t.Fatalf("missing terminal error: %s", tui.err)
	}
}

func TestWriteCountsOnlyBelowMarker(t *testing.T) {
	tmp := t.TempDir()
	structure := filepath.Join(tmp, "structure.json")
	drafts := filepath.Join(tmp, "drafts")
	writeStructure(t, structure, 1, 1)
	editor := filepath.Join(tmp, "editor.sh")
	if err := os.WriteFile(editor, []byte("#!/usr/bin/env bash\nprintf 'x' >> \"$1\"\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	env := map[string]string{
		"XDG_CONFIG_HOME": filepath.Join(tmp, "xdg"),
		"EDITOR":          editor,
		"VISUAL":          "",
	}

	result := runCommand(t, tmp, env, "write", structure, "drafts", drafts, "first")
	draftPath := filepath.Join(drafts, "00-one", "01.md")
	text, err := os.ReadFile(draftPath)
	if err != nil {
		t.Fatal(err)
	}

	if result.code != 0 {
		t.Fatalf("write failed: code=%d out=%s err=%s", result.code, result.out, result.err)
	}
	if !strings.Contains(string(text), "writenow: vim wraps prose at 79 columns") {
		t.Fatalf("missing writenow scaffold comment:\n%s", text)
	}
	if strings.Contains(string(text), "setlocal tw=79") || strings.Contains(string(text), "textwidth=79") {
		t.Fatalf("draft should not contain legacy vim modeline:\n%s", text)
	}
	for index, line := range strings.Split(string(text), "\n") {
		if len(line) > 79 {
			t.Fatalf("line %d is too long: %d %q", index+1, len(line), line)
		}
	}
	if !strings.Contains(result.out, "done 1/1") {
		t.Fatalf("missing done output:\n%s", result.out)
	}
}

func TestWriteStopsAfterSingleEditorPassWhenStillIncomplete(t *testing.T) {
	tmp := t.TempDir()
	structure := filepath.Join(tmp, "structure.json")
	drafts := filepath.Join(tmp, "drafts")
	writeStructure(t, structure, 20, 1)
	editor := filepath.Join(tmp, "editor.sh")
	if err := os.WriteFile(editor, []byte("#!/usr/bin/env bash\nprintf 'short' >> \"$1\"\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	env := map[string]string{
		"XDG_CONFIG_HOME": filepath.Join(tmp, "xdg"),
		"EDITOR":          editor,
		"VISUAL":          "",
	}

	result := runCommand(t, tmp, env, "write", structure, "drafts", drafts)

	if result.code != 1 {
		t.Fatalf("expected incomplete code, got %d", result.code)
	}
	if !strings.Contains(result.out, "incomplete 5/20") {
		t.Fatalf("missing incomplete output:\n%s", result.out)
	}
}

func TestLegacyConfigAndDraftMarkersAreMigrated(t *testing.T) {
	tmp := t.TempDir()
	xdg := filepath.Join(tmp, "xdg")
	structure := filepath.Join(tmp, "structure.json")
	drafts := filepath.Join(tmp, "drafts")
	writeStructure(t, structure, 5, 1)
	legacyConfigDir := filepath.Join(xdg, "wb")
	if err := os.MkdirAll(legacyConfigDir, 0o755); err != nil {
		t.Fatal(err)
	}
	legacyConfig := `{
  "extension": "md",
  "min_chars": 500,
  "presets": {
    "small": {
      "structure": "` + structure + `",
      "drafts": "` + drafts + `"
    }
  }
}
`
	if err := os.WriteFile(filepath.Join(legacyConfigDir, "config.json"), []byte(legacyConfig), 0o644); err != nil {
		t.Fatal(err)
	}
	draftPath := filepath.Join(drafts, "00-one", "01.md")
	writeCompletedDraft(t, draftPath, "<!-- wb:draft:start -->\nfirst body")

	result := runCommand(t, tmp, map[string]string{"XDG_CONFIG_HOME": xdg}, "list")

	if result.code != 0 {
		t.Fatalf("legacy status failed: code=%d err=%s", result.code, result.err)
	}
	if _, err := os.Stat(filepath.Join(xdg, "writenow", "config.json")); err != nil {
		t.Fatalf("new config was not migrated: %v", err)
	}
	if !strings.Contains(result.out, "progress : 1/1 (100%)") {
		t.Fatalf("legacy marker was not counted:\n%s", result.out)
	}
}

func writeCompletedDraft(t *testing.T, path string, body string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte("# One\n\n"+body+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
}
