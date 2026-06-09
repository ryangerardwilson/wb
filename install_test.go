package writenow_test

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func writeExecutable(t *testing.T, path string, body string) {
	t.Helper()
	if err := os.WriteFile(path, []byte(body), 0o755); err != nil {
		t.Fatal(err)
	}
}

func runInstaller(t *testing.T, homeDir string, pathPrefix string, args ...string) (string, string) {
	t.Helper()
	installer, err := filepath.Abs("install.sh")
	if err != nil {
		t.Fatal(err)
	}
	cmd := exec.Command("/usr/bin/bash", append([]string{installer}, args...)...)
	env := os.Environ()
	env = append(env, "HOME="+homeDir)
	if pathPrefix != "" {
		env = append(env, "PATH="+pathPrefix+":"+os.Getenv("PATH"))
	}
	cmd.Env = env
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("installer failed: %v\n%s", err, out)
	}
	return string(out), ""
}

func TestInstallerVersionPrintsLatestRelease(t *testing.T) {
	tmp := t.TempDir()
	binDir := filepath.Join(tmp, "bin")
	homeDir := filepath.Join(tmp, "home")
	if err := os.MkdirAll(binDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(homeDir, 0o755); err != nil {
		t.Fatal(err)
	}
	writeExecutable(t, filepath.Join(binDir, "curl"), "#!/usr/bin/env bash\nif [[ \"$*\" == *\"releases/latest\"* ]]; then\n  printf 'https://github.com/ryangerardwilson/wb/releases/tag/v0.1.0\\n'\n  exit 0\nfi\necho unexpected curl call >&2\nexit 1\n")

	out, _ := runInstaller(t, homeDir, binDir, "version")

	if strings.TrimSpace(out) != "0.1.0" {
		t.Fatalf("unexpected version output: %q", out)
	}
}

func TestInstallerUpgradeSameVersionUsesWritenow(t *testing.T) {
	tmp := t.TempDir()
	binDir := filepath.Join(tmp, "bin")
	homeDir := filepath.Join(tmp, "home")
	if err := os.MkdirAll(binDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(homeDir, 0o755); err != nil {
		t.Fatal(err)
	}
	writeExecutable(t, filepath.Join(binDir, "curl"), "#!/usr/bin/env bash\nif [[ \"$*\" == *\"releases/latest\"* ]]; then\n  printf 'https://github.com/ryangerardwilson/wb/releases/tag/v0.1.0\\n'\n  exit 0\nfi\necho unexpected curl call >&2\nexit 1\n")
	writeExecutable(t, filepath.Join(binDir, "writenow"), "#!/usr/bin/env bash\nif [[ \"$1\" == \"version\" ]]; then\n  printf '0.1.0\\n'\n  exit 0\nfi\necho unexpected invocation >&2\nexit 1\n")

	out, _ := runInstaller(t, homeDir, binDir, "upgrade")

	if !strings.Contains(out, "already installed") {
		t.Fatalf("missing already-installed output: %s", out)
	}
	if _, err := os.Stat(filepath.Join(homeDir, ".local", "bin", "writenow")); err != nil {
		t.Fatalf("public launcher missing: %v", err)
	}
}

func TestInstallerLocalBinaryInstallWritesManagedLaunchers(t *testing.T) {
	tmp := t.TempDir()
	homeDir := filepath.Join(tmp, "home")
	if err := os.MkdirAll(homeDir, 0o755); err != nil {
		t.Fatal(err)
	}
	bashrc := filepath.Join(homeDir, ".bashrc")
	if err := os.WriteFile(bashrc, []byte("# existing shell config\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	sourceBinary := filepath.Join(homeDir, "source-binary")
	writeExecutable(t, sourceBinary, "#!/usr/bin/env bash\nif [[ \"${1:-}\" == \"version\" ]]; then\n  printf '0.0.0\\n'\n  exit 0\nfi\nprintf 'writenow:%s\\n' \"$*\"\nexit 0\n")

	out, _ := runInstaller(t, homeDir, "", "from", sourceBinary)

	internalLauncher := filepath.Join(homeDir, ".writenow", "bin", "writenow")
	publicLauncher := filepath.Join(homeDir, ".local", "bin", "writenow")
	if _, err := os.Stat(internalLauncher); err != nil {
		t.Fatalf("internal launcher missing: %v", err)
	}
	if _, err := os.Stat(publicLauncher); err != nil {
		t.Fatalf("public launcher missing: %v", err)
	}
	bashrcText, err := os.ReadFile(bashrc)
	if err != nil {
		t.Fatal(err)
	}
	if string(bashrcText) != "# existing shell config\n" {
		t.Fatalf("installer modified bashrc:\n%s", bashrcText)
	}
	publicText, err := os.ReadFile(publicLauncher)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(publicText), "# Managed by writenow installer local-bin launcher") {
		t.Fatalf("launcher missing managed marker:\n%s", publicText)
	}
	if !strings.Contains(string(publicText), `exec "`+internalLauncher+`" "$@"`) {
		t.Fatalf("launcher points at wrong binary:\n%s", publicText)
	}
	version := exec.Command(publicLauncher, "version")
	version.Env = append(os.Environ(), "HOME="+homeDir)
	versionOut, err := version.Output()
	if err != nil {
		t.Fatalf("installed launcher failed: %v", err)
	}
	if strings.TrimSpace(string(versionOut)) != "0.0.0" {
		t.Fatalf("unexpected installed version: %q", versionOut)
	}
	if !strings.Contains(out, "Manually add to ~/.bashrc if needed: export PATH="+filepath.Join(homeDir, ".local", "bin")+":$PATH") {
		t.Fatalf("missing manual path output:\n%s", out)
	}
}
