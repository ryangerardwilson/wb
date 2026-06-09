package core

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

const (
	AppName                  = "writenow"
	DefaultStructureName     = "structure.json"
	DraftMarker              = "<!-- writenow:draft:start -->"
	LegacyDraftMarker        = "<!-- wb:draft:start -->"
	ProseWrapComment         = "<!-- writenow: vim wraps prose at 79 columns -->"
	LegacyProseWrapComment   = "<!-- wb: vim wraps prose at 79 columns -->"
	ShortVimWrapModeline     = "<!-- vim: setlocal tw=79 cc=79 wrap lbr fo+=t: -->"
	OldVimWrapModeline       = "<!-- vim: setlocal textwidth=79 colorcolumn=79 wrap linebreak formatoptions+=t: -->"
	ScaffoldWidth            = 79
	defaultExtension         = "md"
	defaultMinChars          = 500
	bootstrapStructureIndent = "  "
)

var slugPattern = regexp.MustCompile(`[^a-zA-Z0-9]+`)

type Preset struct {
	Structure string `json:"structure"`
	Drafts    string `json:"drafts"`
}

type AppConfig struct {
	Extension string            `json:"extension"`
	MinChars  int               `json:"min_chars"`
	Presets   map[string]Preset `json:"presets"`
}

type BookTarget struct {
	StructurePath string
	DraftsDir     string
	PresetName    string
}

type Structure struct {
	Title    string
	Settings map[string]any
	Chapters []Chapter
}

type Chapter struct {
	Title        string
	Propositions []string
	MinChars     any
	HasMinChars  bool
}

type Settings struct {
	Extension string
	MinChars  int
}

type WorkItem struct {
	ChapterIndex     int
	PropositionIndex int
	ChapterTitle     string
	Proposition      string
	Path             string
	MinChars         int
	TotalProps       int
}

type TUIProject struct {
	Name          string
	Title         string
	Target        BookTarget
	Items         []WorkItem
	CompleteCount int
	CurrentIndex  int
}

func DefaultAppConfig() AppConfig {
	return AppConfig{
		Extension: defaultExtension,
		MinChars:  defaultMinChars,
		Presets:   map[string]Preset{},
	}
}

func ParseAppConfig(data []byte) (AppConfig, error) {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()

	var raw map[string]json.RawMessage
	if err := decoder.Decode(&raw); err != nil {
		return AppConfig{}, fmt.Errorf("invalid app config: %w", err)
	}
	if raw == nil {
		return AppConfig{}, errors.New("app config must be a JSON object")
	}

	config := DefaultAppConfig()
	if value, ok := raw["extension"]; ok {
		var extension string
		if err := json.Unmarshal(value, &extension); err != nil {
			return AppConfig{}, errors.New("app config extension must be a string")
		}
		config.Extension = extension
	}
	if value, ok := raw["min_chars"]; ok {
		parsed, err := parseJSONInt(value)
		if err != nil {
			return AppConfig{}, fmt.Errorf("invalid min_chars value: %w", err)
		}
		config.MinChars = parsed
	}
	if value, ok := raw["presets"]; ok {
		var presets map[string]Preset
		if err := json.Unmarshal(value, &presets); err != nil {
			return AppConfig{}, errors.New("app config presets must be a JSON object")
		}
		if presets == nil {
			presets = map[string]Preset{}
		}
		config.Presets = presets
	}
	if config.Presets == nil {
		config.Presets = map[string]Preset{}
	}
	return config, nil
}

func FormatAppConfig(config AppConfig) []byte {
	if config.Extension == "" {
		config.Extension = defaultExtension
	}
	if config.Presets == nil {
		config.Presets = map[string]Preset{}
	}
	data, _ := json.MarshalIndent(config, "", "  ")
	return append(data, '\n')
}

func LoadStructure(path string) (Structure, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return Structure{}, fmt.Errorf("structure not found: %s\nrun writenow init <structure_json>", path)
		}
		return Structure{}, err
	}

	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	var raw map[string]any
	if err := decoder.Decode(&raw); err != nil {
		return Structure{}, fmt.Errorf("invalid JSON in %s: %w", path, err)
	}
	if raw == nil {
		return Structure{}, errors.New("structure root must be a JSON object")
	}

	structure := Structure{
		Title:    stringValue(raw["title"], "Untitled"),
		Settings: map[string]any{},
	}
	if value, exists := raw["settings"]; exists && value != nil {
		settings, ok := value.(map[string]any)
		if !ok {
			return Structure{}, errors.New("structure settings must be an object")
		}
		structure.Settings = settings
	}

	chaptersRaw, ok := raw["chapters"].([]any)
	if !ok || len(chaptersRaw) == 0 {
		return Structure{}, errors.New("structure must contain a non-empty chapters array")
	}

	for index, chapterRaw := range chaptersRaw {
		chapterMap, ok := chapterRaw.(map[string]any)
		if !ok {
			return Structure{}, fmt.Errorf("chapter %d must be an object", index+1)
		}
		title := stringValue(chapterMap["title"], fmt.Sprintf("Chapter %d", index+1))
		propositionsRaw, ok := chapterMap["propositions"].([]any)
		if !ok || len(propositionsRaw) == 0 {
			return Structure{}, fmt.Errorf("%s: propositions must be a non-empty array", title)
		}
		propositions := make([]string, 0, len(propositionsRaw))
		for propIndex, propositionRaw := range propositionsRaw {
			text := strings.TrimSpace(fmt.Sprint(propositionRaw))
			if text == "" {
				return Structure{}, fmt.Errorf("%s: empty proposition %d", title, propIndex+1)
			}
			propositions = append(propositions, text)
		}
		chapter := Chapter{Title: title, Propositions: propositions}
		if value, ok := chapterMap["min_chars"]; ok {
			chapter.MinChars = value
			chapter.HasMinChars = true
		}
		structure.Chapters = append(structure.Chapters, chapter)
	}

	return structure, nil
}

func StructureSettings(structure Structure, appConfig AppConfig) (Settings, error) {
	extension := strings.TrimPrefix(fmt.Sprint(appConfig.Extension), ".")
	if extension == "" {
		extension = defaultExtension
	}
	minChars := appConfig.MinChars
	if minChars == 0 {
		minChars = defaultMinChars
	}

	if value, ok := structure.Settings["extension"]; ok {
		extension = strings.TrimPrefix(fmt.Sprint(value), ".")
		if extension == "" {
			extension = defaultExtension
		}
	}
	if value, ok := structure.Settings["min_chars"]; ok {
		parsed, err := parseAnyInt(value)
		if err != nil {
			return Settings{}, fmt.Errorf("invalid min_chars value: %v", value)
		}
		minChars = parsed
	}
	return Settings{Extension: extension, MinChars: minChars}, nil
}

func WorkItems(target BookTarget, structure Structure, appConfig AppConfig) ([]WorkItem, error) {
	settings, err := StructureSettings(structure, appConfig)
	if err != nil {
		return nil, err
	}

	items := make([]WorkItem, 0)
	for chapterIndex, chapter := range structure.Chapters {
		chapterMinChars := settings.MinChars
		if chapter.HasMinChars {
			parsed, err := parseAnyInt(chapter.MinChars)
			if err != nil {
				return nil, fmt.Errorf("invalid min_chars value: %v", chapter.MinChars)
			}
			chapterMinChars = parsed
		}

		chapterDir := filepath.Join(target.DraftsDir, fmt.Sprintf("%02d-%s", chapterIndex, Slugify(chapter.Title)))
		for propositionIndex, proposition := range chapter.Propositions {
			items = append(items, WorkItem{
				ChapterIndex:     chapterIndex,
				PropositionIndex: propositionIndex + 1,
				ChapterTitle:     chapter.Title,
				Proposition:      proposition,
				Path:             filepath.Join(chapterDir, fmt.Sprintf("%02d.%s", propositionIndex+1, settings.Extension)),
				MinChars:         chapterMinChars,
				TotalProps:       len(chapter.Propositions),
			})
		}
	}
	return items, nil
}

func LoadTarget(target BookTarget, appConfig AppConfig) (Structure, []WorkItem, error) {
	structure, err := LoadStructure(target.StructurePath)
	if err != nil {
		return Structure{}, nil, err
	}
	items, err := WorkItems(target, structure, appConfig)
	if err != nil {
		return Structure{}, nil, err
	}
	return structure, items, nil
}

func Slugify(value string) string {
	slug := strings.Trim(slugPattern.ReplaceAllString(strings.ToLower(value), "-"), "-")
	if slug == "" {
		return "section"
	}
	return slug
}

func DraftBody(path string) (string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return "", nil
		}
		return "", err
	}
	content := string(data)
	body, ok := bodyAfterMarker(content)
	if !ok {
		return strings.TrimSpace(content), nil
	}
	body = strings.ReplaceAll(body, ProseWrapComment, "")
	body = strings.ReplaceAll(body, LegacyProseWrapComment, "")
	body = strings.ReplaceAll(body, ShortVimWrapModeline, "")
	body = strings.ReplaceAll(body, OldVimWrapModeline, "")
	return strings.TrimSpace(body), nil
}

func CharCount(path string) (int, error) {
	body, err := DraftBody(path)
	if err != nil {
		return 0, err
	}
	return len([]rune(body)), nil
}

func ItemComplete(item WorkItem) (bool, error) {
	count, err := CharCount(item.Path)
	if err != nil {
		return false, err
	}
	return count >= item.MinChars, nil
}

func CompleteCount(items []WorkItem) (int, error) {
	complete := 0
	for _, item := range items {
		done, err := ItemComplete(item)
		if err != nil {
			return 0, err
		}
		if done {
			complete++
		}
	}
	return complete, nil
}

func NextIncomplete(items []WorkItem) (*WorkItem, int, error) {
	for index, item := range items {
		done, err := ItemComplete(item)
		if err != nil {
			return nil, 0, err
		}
		if !done {
			itemCopy := item
			return &itemCopy, index, nil
		}
	}
	return nil, -1, nil
}

func DraftScaffold(item WorkItem, totalProps int) string {
	propLines := WrapDisplayText(item.Proposition, ScaffoldWidth-2)
	if len(propLines) == 0 {
		propLines = []string{""}
	}
	for index, line := range propLines {
		if line == "" {
			propLines[index] = ">"
		} else {
			propLines[index] = "> " + line
		}
	}

	instructions := strings.Join(WrapDisplayText(
		"Write below this marker. The proposition text above is scaffolding and does not count.",
		ScaffoldWidth,
	), "\n")
	charLabel := "characters"
	if item.MinChars == 1 {
		charLabel = "character"
	}

	return fmt.Sprintf(`# %s

%s

Proposition %d of %d

## Proposition

%s

## Draft

%s
Completion requires at least %d %s below the marker.

%s
`, item.ChapterTitle, ProseWrapComment, item.PropositionIndex, totalProps, strings.Join(propLines, "\n"), instructions, item.MinChars, charLabel, DraftMarker)
}

func NormalizeDraftScaffold(item WorkItem, totalProps int) error {
	data, err := os.ReadFile(item.Path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}
	body, ok := bodyAfterMarker(string(data))
	if !ok {
		return nil
	}
	body = strings.ReplaceAll(body, ProseWrapComment, "")
	body = strings.ReplaceAll(body, LegacyProseWrapComment, "")
	body = strings.ReplaceAll(body, ShortVimWrapModeline, "")
	body = strings.ReplaceAll(body, OldVimWrapModeline, "")
	body = strings.TrimLeft(body, "\n")
	return os.WriteFile(item.Path, []byte(DraftScaffold(item, totalProps)+body), 0o644)
}

func EnsureDraft(item WorkItem, totalProps int) error {
	if _, err := os.Stat(item.Path); err == nil {
		return NormalizeDraftScaffold(item, totalProps)
	} else if !os.IsNotExist(err) {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(item.Path), 0o755); err != nil {
		return err
	}
	return os.WriteFile(item.Path, []byte(DraftScaffold(item, totalProps)), 0o644)
}

func ProjectRow(project TUIProject) string {
	total := len(project.Items)
	percent := 0
	if total > 0 {
		percent = int(math.Round(float64(project.CompleteCount) / float64(total) * 100))
	}
	return fmt.Sprintf("%s  %d/%d (%d%%)  %s", project.Name, project.CompleteCount, total, percent, project.Title)
}

func ItemHeader(project TUIProject, index int) (string, error) {
	item := project.Items[index]
	count, err := CharCount(item.Path)
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("%s - %d/%d %s %d/%d", project.Title, index+1, len(project.Items), StatusWord(item), count, item.MinChars), nil
}

func ItemLines(project TUIProject, index int, width int) ([]string, error) {
	item := project.Items[index]
	body, err := DraftBody(item.Path)
	if err != nil {
		return nil, err
	}
	lines := []string{
		fmt.Sprintf("%s / %d", item.ChapterTitle, item.PropositionIndex),
		fmt.Sprintf("draft: %s", MutedPath(item.Path)),
		"",
		"Proposition",
		"",
	}
	lines = append(lines, WrapDisplayText(item.Proposition, width)...)
	lines = append(lines, "", "Draft", "")
	if body == "" {
		lines = append(lines, "(empty draft)")
	} else {
		lines = append(lines, WrapDisplayText(body, width)...)
	}
	return lines, nil
}

func StatusWord(item WorkItem) string {
	done, err := ItemComplete(item)
	if err != nil || !done {
		return "todo"
	}
	return "done"
}

func BuildTUIProjects(config AppConfig, configPath string) ([]TUIProject, error) {
	names := make([]string, 0, len(config.Presets))
	for name := range config.Presets {
		names = append(names, name)
	}
	sort.Slice(names, func(i, j int) bool {
		return strings.ToLower(names[i]) < strings.ToLower(names[j])
	})

	base := filepath.Dir(configPath)
	projects := make([]TUIProject, 0, len(names))
	for _, name := range names {
		preset := config.Presets[name]
		target, err := TargetFromPreset(name, preset, base)
		if err != nil {
			continue
		}
		structure, items, err := LoadTarget(target, config)
		if err != nil {
			return nil, err
		}
		complete, err := CompleteCount(items)
		if err != nil {
			return nil, err
		}
		_, currentIndex, err := NextIncomplete(items)
		if err != nil {
			return nil, err
		}
		if currentIndex < 0 {
			currentIndex = max(len(items)-1, 0)
		}
		projects = append(projects, TUIProject{
			Name:          name,
			Title:         structure.Title,
			Target:        target,
			Items:         items,
			CompleteCount: complete,
			CurrentIndex:  currentIndex,
		})
	}
	return projects, nil
}

func TargetFromPreset(name string, preset Preset, base string) (BookTarget, error) {
	if strings.TrimSpace(preset.Structure) == "" {
		return BookTarget{}, fmt.Errorf("preset %q requires a structure path", name)
	}
	if strings.TrimSpace(preset.Drafts) == "" {
		return BookTarget{}, fmt.Errorf("preset %q requires a drafts dir", name)
	}
	structure, err := ResolvePath(preset.Structure, base)
	if err != nil {
		return BookTarget{}, err
	}
	drafts, err := ResolvePath(preset.Drafts, base)
	if err != nil {
		return BookTarget{}, err
	}
	return BookTarget{StructurePath: structure, DraftsDir: drafts, PresetName: name}, nil
}

func ResolveArgPath(value string) (string, error) {
	wd, err := os.Getwd()
	if err != nil {
		return "", err
	}
	return ResolvePath(value, wd)
}

func ResolvePath(value string, base string) (string, error) {
	if strings.TrimSpace(value) == "" {
		return "", errors.New("path must not be empty")
	}
	path := expandHome(value)
	if !filepath.IsAbs(path) {
		path = filepath.Join(base, path)
	}
	return filepath.Abs(path)
}

func MutedPath(path string) string {
	absPath, err := filepath.Abs(path)
	if err != nil {
		return path
	}
	wd, err := os.Getwd()
	if err != nil {
		return absPath
	}
	absWd, err := filepath.Abs(wd)
	if err != nil {
		return absPath
	}
	rel, err := filepath.Rel(absWd, absPath)
	if err == nil && rel != "." && !strings.HasPrefix(rel, ".."+string(os.PathSeparator)) && rel != ".." {
		return rel
	}
	if rel == "." {
		return "."
	}
	return absPath
}

func WrapDisplayText(text string, width int) []string {
	if width < 20 {
		width = 20
	}
	var lines []string
	for _, rawLine := range strings.Split(text, "\n") {
		if strings.TrimSpace(rawLine) == "" {
			lines = append(lines, "")
			continue
		}
		lines = append(lines, wrapLine(rawLine, width)...)
	}
	return lines
}

func BootstrapStructure() []byte {
	data := map[string]any{
		"title": "Untitled Book",
		"settings": map[string]any{
			"extension": defaultExtension,
			"min_chars": defaultMinChars,
		},
		"chapters": []any{
			map[string]any{
				"title": "Chapter One",
				"propositions": []string{
					"State the first proposition this chapter needs to prove.",
				},
			},
		},
	}
	encoded, _ := json.MarshalIndent(data, "", bootstrapStructureIndent)
	return append(encoded, '\n')
}

func Percent(done int, total int) int {
	if total == 0 {
		return 0
	}
	return int(math.Round(float64(done) / float64(total) * 100))
}

func bodyAfterMarker(content string) (string, bool) {
	if strings.Contains(content, DraftMarker) {
		return strings.SplitN(content, DraftMarker, 2)[1], true
	}
	if strings.Contains(content, LegacyDraftMarker) {
		return strings.SplitN(content, LegacyDraftMarker, 2)[1], true
	}
	return "", false
}

func stringValue(value any, fallback string) string {
	if value == nil {
		return fallback
	}
	text := strings.TrimSpace(fmt.Sprint(value))
	if text == "" {
		return fallback
	}
	return text
}

func parseJSONInt(raw json.RawMessage) (int, error) {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var value any
	if err := decoder.Decode(&value); err != nil {
		return 0, err
	}
	return parseAnyInt(value)
}

func parseAnyInt(value any) (int, error) {
	switch typed := value.(type) {
	case json.Number:
		parsed, err := typed.Int64()
		if err != nil {
			return 0, err
		}
		return int(parsed), nil
	case float64:
		if typed != math.Trunc(typed) {
			return 0, fmt.Errorf("%v is not an integer", typed)
		}
		return int(typed), nil
	case int:
		return typed, nil
	case int64:
		return int(typed), nil
	case string:
		return strconv.Atoi(strings.TrimSpace(typed))
	default:
		return 0, fmt.Errorf("%v is not an integer", value)
	}
}

func expandHome(path string) string {
	if path == "~" {
		if home, err := os.UserHomeDir(); err == nil && home != "" {
			return home
		}
	}
	if len(path) > 2 && path[0] == '~' && os.IsPathSeparator(path[1]) {
		if home, err := os.UserHomeDir(); err == nil && home != "" {
			return filepath.Join(home, path[2:])
		}
	}
	return path
}

func wrapLine(line string, width int) []string {
	words := strings.Fields(line)
	if len(words) == 0 {
		return []string{""}
	}
	var lines []string
	current := ""
	for _, word := range words {
		for len([]rune(word)) > width {
			prefix := string([]rune(word)[:width])
			if current != "" {
				lines = append(lines, current)
				current = ""
			}
			lines = append(lines, prefix)
			word = string([]rune(word)[width:])
		}
		if current == "" {
			current = word
			continue
		}
		if len([]rune(current))+1+len([]rune(word)) <= width {
			current += " " + word
			continue
		}
		lines = append(lines, current)
		current = word
	}
	if current != "" {
		lines = append(lines, current)
	}
	return lines
}
