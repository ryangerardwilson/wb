package app

import (
	"fmt"
	"os/exec"

	"github.com/charmbracelet/bubbles/key"
	tea "github.com/charmbracelet/bubbletea"

	"github.com/ryangerardwilson/wb/internal/components/l1"
	"github.com/ryangerardwilson/wb/internal/components/l3"
	"github.com/ryangerardwilson/wb/internal/core"
)

type mode int

const (
	projectMode mode = iota
	readerMode
)

type keyMap struct {
	Up       key.Binding
	Down     key.Binding
	Select   key.Binding
	Next     key.Binding
	Previous key.Binding
	Edit     key.Binding
	Books    key.Binding
	Quit     key.Binding
	Top      key.Binding
	Bottom   key.Binding
}

type Model struct {
	keys     keyMap
	theme    l1.Theme
	projects []core.TUIProject
	mode     mode
	selected int
	index    int
	scroll   int
	width    int
	height   int
	err      error
	message  string
}

type editorFinishedMsg struct {
	err error
}

func defaultKeyMap() keyMap {
	return keyMap{
		Up: key.NewBinding(
			key.WithKeys("up", "k"),
			key.WithHelp("k", "up"),
		),
		Down: key.NewBinding(
			key.WithKeys("down", "j"),
			key.WithHelp("j", "down"),
		),
		Select: key.NewBinding(
			key.WithKeys("enter"),
			key.WithHelp("enter", "select"),
		),
		Next: key.NewBinding(
			key.WithKeys("n"),
			key.WithHelp("n", "next"),
		),
		Previous: key.NewBinding(
			key.WithKeys("p"),
			key.WithHelp("p", "previous"),
		),
		Edit: key.NewBinding(
			key.WithKeys("e"),
			key.WithHelp("e", "edit"),
		),
		Books: key.NewBinding(
			key.WithKeys("b"),
			key.WithHelp("b", "books"),
		),
		Quit: key.NewBinding(
			key.WithKeys("q", "ctrl+c", "esc"),
			key.WithHelp("q", "quit"),
		),
		Top: key.NewBinding(
			key.WithKeys("g"),
			key.WithHelp("g", "top"),
		),
		Bottom: key.NewBinding(
			key.WithKeys("G"),
			key.WithHelp("G", "bottom"),
		),
	}
}

func NewModel(projects []core.TUIProject) Model {
	return Model{
		keys:     defaultKeyMap(),
		theme:    l1.DefaultTheme(),
		projects: projects,
		width:    80,
		height:   24,
	}
}

func (m Model) Init() tea.Cmd {
	return nil
}

func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
	case editorFinishedMsg:
		if msg.err != nil {
			m.err = msg.err
			m.message = ""
			return m, nil
		}
		m.err = nil
		m.message = "saved draft"
		m.refreshSelectedProject()
	case tea.KeyMsg:
		switch {
		case key.Matches(msg, m.keys.Quit):
			return m, tea.Quit
		}
		if m.mode == projectMode {
			m.updatePicker(msg)
		} else {
			if cmd := m.updateReader(msg); cmd != nil {
				return m, cmd
			}
		}
	}
	return m, nil
}

func (m Model) View() string {
	if m.mode == projectMode {
		return l3.RenderPicker(m.theme, l3.PickerView{
			Projects: m.projects,
			Selected: m.selected,
			Height:   m.height,
		})
	}
	return l3.RenderReader(m.theme, l3.ReaderView{
		Project: m.projects[m.selected],
		Index:   m.index,
		Scroll:  m.scroll,
		Width:   m.width,
		Height:  m.height,
		Message: m.message,
		Error:   errorText(m.err),
	})
}

func (m *Model) updatePicker(msg tea.KeyMsg) {
	if len(m.projects) == 0 {
		return
	}
	switch {
	case key.Matches(msg, m.keys.Up):
		m.selected = max(m.selected-1, 0)
	case key.Matches(msg, m.keys.Down):
		m.selected = min(m.selected+1, len(m.projects)-1)
	case key.Matches(msg, m.keys.Select):
		m.mode = readerMode
		m.index = m.projects[m.selected].CurrentIndex
		m.scroll = 0
	}
}

func (m *Model) updateReader(msg tea.KeyMsg) tea.Cmd {
	project := m.projects[m.selected]
	switch {
	case key.Matches(msg, m.keys.Books):
		m.mode = projectMode
		m.scroll = 0
	case key.Matches(msg, m.keys.Next):
		m.index = min(m.index+1, len(project.Items)-1)
		m.scroll = 0
		m.message = ""
		m.err = nil
	case key.Matches(msg, m.keys.Previous):
		m.index = max(m.index-1, 0)
		m.scroll = 0
		m.message = ""
		m.err = nil
	case key.Matches(msg, m.keys.Edit):
		m.message = ""
		m.err = nil
		return m.openDraftEditor()
	case key.Matches(msg, m.keys.Down):
		m.scroll++
	case key.Matches(msg, m.keys.Up):
		m.scroll = max(m.scroll-1, 0)
	case key.Matches(msg, m.keys.Top):
		m.scroll = 0
	case key.Matches(msg, m.keys.Bottom):
		m.scroll = 1 << 30
	}
	return nil
}

func (m Model) openDraftEditor() tea.Cmd {
	if len(m.projects) == 0 {
		return nil
	}
	project := m.projects[m.selected]
	if len(project.Items) == 0 {
		return nil
	}
	index := min(max(m.index, 0), len(project.Items)-1)
	item := project.Items[index]
	totalProps := item.TotalProps
	if totalProps <= 0 {
		totalProps = 1
	}
	if err := core.EnsureDraft(item, totalProps); err != nil {
		return func() tea.Msg {
			return editorFinishedMsg{err: err}
		}
	}
	cmd := exec.Command("vim", "+setlocal textwidth=79 colorcolumn=79 wrap linebreak formatoptions+=t", item.Path)
	return tea.ExecProcess(cmd, func(err error) tea.Msg {
		return editorFinishedMsg{err: err}
	})
}

func (m *Model) refreshSelectedProject() {
	if len(m.projects) == 0 {
		return
	}
	project := m.projects[m.selected]
	complete, err := core.CompleteCount(project.Items)
	if err != nil {
		m.err = err
		m.message = ""
		return
	}
	_, currentIndex, err := core.NextIncomplete(project.Items)
	if err != nil {
		m.err = err
		m.message = ""
		return
	}
	if currentIndex < 0 {
		currentIndex = max(len(project.Items)-1, 0)
	}
	project.CompleteCount = complete
	project.CurrentIndex = currentIndex
	m.projects[m.selected] = project
	if len(project.Items) > 0 {
		m.index = min(m.index, len(project.Items)-1)
	}
}

func errorText(err error) string {
	if err == nil {
		return ""
	}
	return fmt.Sprint(err)
}

func Run(projects []core.TUIProject) error {
	program := tea.NewProgram(NewModel(projects), tea.WithAltScreen())
	_, err := program.Run()
	return err
}
