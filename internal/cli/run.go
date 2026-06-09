package cli

import (
	"bufio"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"

	"golang.org/x/term"

	"github.com/ryangerardwilson/wb/internal/app"
	"github.com/ryangerardwilson/wb/internal/core"
	"github.com/ryangerardwilson/wb/internal/storage"
	"github.com/ryangerardwilson/wb/internal/version"
)

type Runner struct {
	Out        io.Writer
	Err        io.Writer
	In         io.Reader
	OpenEditor func(path string) int
}

func NewRunner(out io.Writer, errOut io.Writer) Runner {
	return Runner{
		Out:        out,
		Err:        errOut,
		In:         os.Stdin,
		OpenEditor: openEditor,
	}
}

func (r Runner) Run(args []string) int {
	if len(args) == 0 {
		WriteHelp(r.Out)
		return 0
	}

	switch args[0] {
	case "help":
		if len(args) != 1 {
			return r.fail("help takes no arguments")
		}
		WriteHelp(r.Out)
		return 0
	case "version":
		if len(args) != 1 {
			return r.fail("version takes no arguments")
		}
		_, _ = fmt.Fprintln(r.Out, version.Version)
		return 0
	case "upgrade":
		if len(args) != 1 {
			return r.fail("upgrade takes no arguments")
		}
		return r.upgrade()
	case "init":
		return r.commandInit(args[1:])
	case "preset":
		return r.commandPreset(args[1:])
	case "config":
		return r.commandConfig(args[1:])
	case "list":
		return r.commandProjectList(args[1:])
	case "start":
		return r.commandStart(args[1:])
	case "tui":
		return r.commandTUI(args[1:])
	case "write":
		target, rest, err := parseStructureDrafts(args[1:], "valid shape: writenow write <structure_json> drafts <drafts_dir> [first]")
		if err != nil {
			return r.fail(err.Error())
		}
		return r.commandWrite(target, rest)
	case "export":
		target, rest, err := parseStructureDrafts(args[1:], "valid shape: writenow export <structure_json> drafts <drafts_dir> [all] [to <output_md>]")
		if err != nil {
			return r.fail(err.Error())
		}
		return r.commandExport(target, rest)
	default:
		return r.fail(fmt.Sprintf("unknown action %q\n\nRun: writenow help", args[0]))
	}
}

func (r Runner) commandInit(args []string) int {
	if len(args) > 1 {
		return r.fail("valid shape: writenow init [structure_json]")
	}
	pathArg := core.DefaultStructureName
	if len(args) == 1 {
		pathArg = args[0]
	}
	path, err := core.ResolveArgPath(pathArg)
	if err != nil {
		return r.fail(err.Error())
	}
	if _, err := os.Stat(path); err == nil {
		return r.failWithCode(fmt.Sprintf("structure already exists: %s", path), 1)
	} else if !os.IsNotExist(err) {
		return r.fail(err.Error())
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return r.fail(err.Error())
	}
	if err := os.WriteFile(path, core.BootstrapStructure(), 0o644); err != nil {
		return r.fail(err.Error())
	}
	_, _ = fmt.Fprintln(r.Out, core.MutedPath(path))
	return 0
}

func (r Runner) commandPreset(args []string) int {
	if len(args) != 6 || args[0] != "save" || args[2] != "structure" || args[4] != "drafts" {
		return r.fail("valid shape: writenow preset save <name> structure <structure_json> drafts <drafts_dir>")
	}
	name := strings.TrimSpace(args[1])
	if name == "" {
		return r.fail("preset name must not be empty")
	}
	structurePath, err := core.ResolveArgPath(args[3])
	if err != nil {
		return r.fail(err.Error())
	}
	draftsDir, err := core.ResolveArgPath(args[5])
	if err != nil {
		return r.fail(err.Error())
	}
	store, ok := r.store()
	if !ok {
		return 1
	}
	config, err := store.LoadConfig()
	if err != nil {
		return r.fail(err.Error())
	}
	if config.Presets == nil {
		config.Presets = map[string]core.Preset{}
	}
	config.Presets[name] = core.Preset{Structure: structurePath, Drafts: draftsDir}
	if err := store.SaveConfig(config); err != nil {
		return r.fail(err.Error())
	}
	_, _ = fmt.Fprintf(r.Out, "preset   : %s\n", name)
	_, _ = fmt.Fprintf(r.Out, "structure: %s\n", core.MutedPath(structurePath))
	_, _ = fmt.Fprintf(r.Out, "drafts   : %s\n", core.MutedPath(draftsDir))
	return 0
}

func (r Runner) commandConfig(args []string) int {
	if len(args) != 0 {
		return r.fail("valid shape: writenow config")
	}
	store, ok := r.store()
	if !ok {
		return 1
	}
	path, err := store.EnsureConfig()
	if err != nil {
		return r.fail(err.Error())
	}
	return r.OpenEditor(path)
}

func (r Runner) commandProjectList(args []string) int {
	if len(args) != 0 {
		return r.fail("valid shape: writenow list")
	}
	store, ok := r.store()
	if !ok {
		return 1
	}
	config, err := store.LoadConfig()
	if err != nil {
		return r.fail(err.Error())
	}
	if len(config.Presets) == 0 {
		_, _ = fmt.Fprintln(r.Out, "no writenow books saved")
		_, _ = fmt.Fprintln(r.Out, "save one with: writenow preset save <name> structure <structure_json> drafts <drafts_dir>")
		return 0
	}

	_, _ = fmt.Fprintln(r.Out, "writenow books")
	names := sortedPresetNames(config.Presets)
	base := filepath.Dir(store.Paths.ConfigPath)
	for index, name := range names {
		if index > 0 {
			_, _ = fmt.Fprintln(r.Out)
		}
		_, _ = fmt.Fprintf(r.Out, "%d. %s\n", index+1, name)
		target, err := core.TargetFromPreset(name, config.Presets[name], base)
		if err != nil {
			_, _ = fmt.Fprintln(r.Out, "  status   : invalid preset")
			_, _ = fmt.Fprintf(r.Out, "  error    : %s\n", err)
			continue
		}
		structure, items, err := core.LoadTarget(target, config)
		if err != nil {
			return r.fail(err.Error())
		}
		complete, err := core.CompleteCount(items)
		if err != nil {
			return r.fail(err.Error())
		}
		current, _, err := core.NextIncomplete(items)
		if err != nil {
			return r.fail(err.Error())
		}
		_, _ = fmt.Fprintf(r.Out, "  title    : %s\n", structure.Title)
		_, _ = fmt.Fprintf(r.Out, "  progress : %d/%d (%d%%)\n", complete, len(items), core.Percent(complete, len(items)))
		if current == nil {
			_, _ = fmt.Fprintln(r.Out, "  next     : none")
		} else {
			count, err := core.CharCount(current.Path)
			if err != nil {
				return r.fail(err.Error())
			}
			_, _ = fmt.Fprintf(r.Out, "  next     : %s / %d\n", current.ChapterTitle, current.PropositionIndex)
			_, _ = fmt.Fprintf(r.Out, "  chars    : %d/%d\n", count, current.MinChars)
		}
		_, _ = fmt.Fprintf(r.Out, "  structure: %s\n", core.MutedPath(target.StructurePath))
		_, _ = fmt.Fprintf(r.Out, "  drafts   : %s\n", core.MutedPath(target.DraftsDir))
	}
	return 0
}

func (r Runner) commandStart(args []string) int {
	if len(args) > 1 {
		return r.fail("valid shape: writenow start [booknumber]")
	}
	store, ok := r.store()
	if !ok {
		return 1
	}
	config, err := store.LoadConfig()
	if err != nil {
		return r.fail(err.Error())
	}
	projects, err := core.BuildTUIProjects(config, store.Paths.ConfigPath)
	if err != nil {
		return r.fail(err.Error())
	}
	if len(projects) == 0 {
		_, _ = fmt.Fprintln(r.Out, "no writenow books saved")
		_, _ = fmt.Fprintln(r.Out, "save one with: writenow preset save <name> structure <structure_json> drafts <drafts_dir>")
		return 0
	}

	rawNumber := ""
	if len(args) == 1 {
		rawNumber = strings.TrimSpace(args[0])
	} else {
		r.writeBookChoices(projects)
		_, _ = fmt.Fprint(r.Out, "book number: ")
		scanner := bufio.NewScanner(r.In)
		if !scanner.Scan() {
			if err := scanner.Err(); err != nil {
				return r.fail(err.Error())
			}
			return r.fail("book number is required")
		}
		rawNumber = strings.TrimSpace(scanner.Text())
	}

	bookNumber, err := strconv.Atoi(rawNumber)
	if err != nil || bookNumber < 1 || bookNumber > len(projects) {
		return r.fail(fmt.Sprintf("book number must be 1-%d", len(projects)))
	}
	project := projects[bookNumber-1]
	_, _ = fmt.Fprintf(r.Out, "start %d: %s\n", bookNumber, project.Name)
	return r.commandWriteWithConfig(project.Target, config, nil)
}

func (r Runner) writeBookChoices(projects []core.TUIProject) {
	_, _ = fmt.Fprintln(r.Out, "writenow books")
	for index, project := range projects {
		_, _ = fmt.Fprintf(r.Out, "%d. %s\n", index+1, core.ProjectRow(project))
	}
}

func (r Runner) commandTUI(args []string) int {
	if len(args) != 0 {
		return r.fail("valid shape: writenow tui")
	}
	store, ok := r.store()
	if !ok {
		return 1
	}
	config, err := store.LoadConfig()
	if err != nil {
		return r.fail(err.Error())
	}
	projects, err := core.BuildTUIProjects(config, store.Paths.ConfigPath)
	if err != nil {
		return r.fail(err.Error())
	}
	if len(projects) == 0 {
		_, _ = fmt.Fprintln(r.Out, "no writenow projects saved")
		_, _ = fmt.Fprintln(r.Out, "save one with: writenow preset save <name> structure <structure_json> drafts <drafts_dir>")
		return 0
	}
	if !term.IsTerminal(int(os.Stdin.Fd())) || !term.IsTerminal(int(os.Stdout.Fd())) {
		return r.failWithCode("writenow tui requires an interactive terminal", 1)
	}
	if err := app.Run(projects); err != nil {
		return r.fail(err.Error())
	}
	return 0
}

func (r Runner) commandWrite(target core.BookTarget, args []string) int {
	store, ok := r.store()
	if !ok {
		return 1
	}
	config, err := store.LoadConfig()
	if err != nil {
		return r.fail(err.Error())
	}
	return r.commandWriteWithConfig(target, config, args)
}

func (r Runner) commandWriteWithConfig(target core.BookTarget, config core.AppConfig, args []string) int {
	once := false
	if len(args) == 1 && args[0] == "first" {
		once = true
	} else if len(args) != 0 {
		return r.fail("valid shape: writenow write <structure_json> drafts <drafts_dir> [first]")
	}

	structure, items, err := core.LoadTarget(target, config)
	if err != nil {
		return r.fail(err.Error())
	}

	for {
		item, _, err := core.NextIncomplete(items)
		if err != nil {
			return r.fail(err.Error())
		}
		if item == nil {
			_, _ = fmt.Fprintln(r.Out, "complete all propositions")
			return 0
		}

		totalProps := len(structure.Chapters[item.ChapterIndex].Propositions)
		if err := core.EnsureDraft(*item, totalProps); err != nil {
			return r.fail(err.Error())
		}
		current, err := core.CharCount(item.Path)
		if err != nil {
			return r.fail(err.Error())
		}
		_, _ = fmt.Fprintf(r.Out, "open %s / %d (%d/%d) %s\n", item.ChapterTitle, item.PropositionIndex, current, item.MinChars, core.MutedPath(item.Path))

		if code := r.OpenEditor(item.Path); code != 0 {
			return code
		}
		current, err = core.CharCount(item.Path)
		if err != nil {
			return r.fail(err.Error())
		}
		if current < item.MinChars {
			_, _ = fmt.Fprintf(r.Out, "incomplete %d/%d; need %d more\n", current, item.MinChars, item.MinChars-current)
			return 1
		}

		_, _ = fmt.Fprintf(r.Out, "done %d/%d\n", current, item.MinChars)
		if once {
			return 0
		}
	}
}

func (r Runner) commandExport(target core.BookTarget, args []string) int {
	store, ok := r.store()
	if !ok {
		return 1
	}
	config, err := store.LoadConfig()
	if err != nil {
		return r.fail(err.Error())
	}
	return r.commandExportWithConfig(target, config, args, "valid shape: writenow export <structure_json> drafts <drafts_dir> [all] [to <output_md>]")
}

func (r Runner) commandExportWithConfig(target core.BookTarget, config core.AppConfig, args []string, shape string) int {
	includeAll, outputPath, err := parseExportArgs(args, shape)
	if err != nil {
		return r.fail(err.Error())
	}
	structure, items, err := core.LoadTarget(target, config)
	if err != nil {
		return r.fail(err.Error())
	}

	chunks := []string{strings.TrimSpace("# " + structure.Title), ""}
	for chapterIndex, chapter := range structure.Chapters {
		chunks = append(chunks, fmt.Sprintf("## %s", chapter.Title), "")
		for _, item := range items {
			if item.ChapterIndex != chapterIndex {
				continue
			}
			body, err := core.DraftBody(item.Path)
			if err != nil {
				return r.fail(err.Error())
			}
			count, err := core.CharCount(item.Path)
			if err != nil {
				return r.fail(err.Error())
			}
			if body == "" && !includeAll {
				continue
			}
			if count < item.MinChars && !includeAll {
				continue
			}
			chunks = append(chunks, body, "")
		}
	}
	output := strings.TrimRight(strings.Join(chunks, "\n"), "\n") + "\n"
	if outputPath != "" {
		if err := os.MkdirAll(filepath.Dir(outputPath), 0o755); err != nil {
			return r.fail(err.Error())
		}
		if err := os.WriteFile(outputPath, []byte(output), 0o644); err != nil {
			return r.fail(err.Error())
		}
		_, _ = fmt.Fprintln(r.Out, core.MutedPath(outputPath))
		return 0
	}
	_, _ = fmt.Fprint(r.Out, output)
	return 0
}

func (r Runner) upgrade() int {
	if installer := os.Getenv("WRITENOW_INSTALLER"); installer != "" {
		return r.runInstaller(installer)
	}
	if _, err := os.Stat("./install.sh"); err == nil {
		return r.runInstaller("./install.sh")
	}
	cmd := exec.Command("bash", "-c", "curl -fsSL https://raw.githubusercontent.com/ryangerardwilson/wb/main/install.sh | bash -s -- upgrade")
	cmd.Stdout = r.Out
	cmd.Stderr = r.Err
	if err := cmd.Run(); err != nil {
		return r.fail(err.Error())
	}
	return 0
}

func (r Runner) runInstaller(installer string) int {
	cmd := exec.Command(installer, "upgrade")
	cmd.Stdout = r.Out
	cmd.Stderr = r.Err
	if err := cmd.Run(); err != nil {
		return r.fail(err.Error())
	}
	return 0
}

func (r Runner) store() (storage.Store, bool) {
	paths, err := storage.DefaultPaths()
	if err != nil {
		_ = r.fail(err.Error())
		return storage.Store{}, false
	}
	return storage.New(paths), true
}

func (r Runner) fail(message string) int {
	return r.failWithCode(message, 1)
}

func (r Runner) failWithCode(message string, code int) int {
	message = strings.TrimSpace(message)
	if message == "" {
		message = "unknown error"
	}
	_, _ = fmt.Fprintf(r.Err, "writenow: %s\n", message)
	return code
}

func parseStructureDrafts(args []string, shape string) (core.BookTarget, []string, error) {
	if len(args) < 3 || args[1] != "drafts" {
		return core.BookTarget{}, nil, errors.New(shape)
	}
	structurePath, err := core.ResolveArgPath(args[0])
	if err != nil {
		return core.BookTarget{}, nil, err
	}
	draftsDir, err := core.ResolveArgPath(args[2])
	if err != nil {
		return core.BookTarget{}, nil, err
	}
	return core.BookTarget{StructurePath: structurePath, DraftsDir: draftsDir}, args[3:], nil
}

func parseExportArgs(args []string, shape string) (bool, string, error) {
	includeAll := false
	outputPath := ""
	for index := 0; index < len(args); {
		switch args[index] {
		case "all":
			includeAll = true
			index++
		case "to":
			if outputPath != "" {
				return false, "", errors.New(shape)
			}
			if index+1 >= len(args) {
				return false, "", errors.New("to requires an output path")
			}
			path, err := core.ResolveArgPath(args[index+1])
			if err != nil {
				return false, "", err
			}
			outputPath = path
			index += 2
		default:
			return false, "", errors.New(shape)
		}
	}
	return includeAll, outputPath, nil
}

func sortedPresetNames(presets map[string]core.Preset) []string {
	names := make([]string, 0, len(presets))
	for name := range presets {
		names = append(names, name)
	}
	sort.Slice(names, func(i, j int) bool {
		return strings.ToLower(names[i]) < strings.ToLower(names[j])
	})
	return names
}

func openEditor(path string) int {
	command := resolveEditorCommand()
	executable := filepath.Base(command[0])
	if executable == "vim" || executable == "nvim" || executable == "vi" {
		command = append(command, "+setlocal textwidth=79 colorcolumn=79 wrap linebreak formatoptions+=t")
	}
	command = append(command, path)
	cmd := exec.Command(command[0], command[1:]...)
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			return exitErr.ExitCode()
		}
		return 1
	}
	return 0
}

func resolveEditorCommand() []string {
	editor := strings.TrimSpace(os.Getenv("VISUAL"))
	if editor == "" {
		editor = strings.TrimSpace(os.Getenv("EDITOR"))
	}
	if editor == "" {
		editor = "vim"
	}
	parts := strings.Fields(editor)
	if len(parts) == 0 {
		return []string{"vim"}
	}
	return parts
}
