package app

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"

	"github.com/ryangerardwilson/wb/internal/core"
)

func TestEditKeyOpensCurrentDraftInVimAndRefreshesProgress(t *testing.T) {
	tmp := t.TempDir()
	draftPath := filepath.Join(tmp, "drafts", "00-one", "01.md")
	item := core.WorkItem{
		ChapterIndex:     0,
		PropositionIndex: 1,
		ChapterTitle:     "One",
		Proposition:      "Argue thing one.",
		Path:             draftPath,
		MinChars:         1,
		TotalProps:       1,
	}
	model := NewModel([]core.TUIProject{{
		Name:  "small",
		Title: "Small",
		Items: []core.WorkItem{item},
	}})
	model.mode = readerMode

	updated, cmd := model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'e'}})
	if cmd == nil {
		t.Fatal("edit key did not return an editor command")
	}
	data, err := os.ReadFile(draftPath)
	if err != nil {
		t.Fatal(err)
	}
	text := string(data)
	if !strings.Contains(text, core.DraftMarker) {
		t.Fatalf("draft was not scaffolded:\n%s", text)
	}
	if err := os.WriteFile(draftPath, []byte(text+"x"), 0o644); err != nil {
		t.Fatal(err)
	}
	updated, _ = updated.Update(editorFinishedMsg{})
	next := updated.(Model)

	data, err = os.ReadFile(draftPath)
	if err != nil {
		t.Fatal(err)
	}
	text = string(data)
	if !strings.HasSuffix(text, "x") {
		t.Fatalf("draft edit was not preserved:\n%s", text)
	}
	if next.projects[0].CompleteCount != 1 {
		t.Fatalf("progress was not refreshed: %d", next.projects[0].CompleteCount)
	}
	if next.message != "saved draft" {
		t.Fatalf("message was not set after edit: %q", next.message)
	}
}
