package search

import (
	"bytes"
	"fmt"
	"io"
	"os"
	"os/exec"
	"strings"

	"github.com/apex/log"
)

// isDeprecated checks if the program version is lower than 1.10.0.
func isDeprecated(version string) bool {
	splitedVersion := strings.Split(version, ".")
	if len(splitedVersion) < 2 {
		return false
	}
	if splitedVersion[0] == "1" && len(splitedVersion[1]) < 2 {
		return true
	}
	return false
}

// SearchVersions outputs available versions of program.
func SearchVersions(program string) error {
	var cmd *exec.Cmd

	if _, err := exec.LookPath("git"); err != nil {
		return fmt.Errorf("'git' is needed for 'tt search' to work")
	}

	if program == "tarantool" {
		cmd = exec.Command("git", "-c", "versionsort.suffix=-", "ls-remote", "--tags", "--sort="+
			"v:refname", "https://github.com/tarantool/tarantool.git")
	} else if program == "tt" {
		cmd = exec.Command("git", "-c", "versionsort.suffix=-", "ls-remote", "--tags", "--sort="+
			"v:refname", "https://github.com/tarantool/tt.git")
	} else {
		return fmt.Errorf("Search supports only tarantool/tt")
	}

	log.Warn("Available versions of " + program + ":")

	readPipe, writePipe, _ := os.Pipe()
	cmd.Stdout = writePipe
	cmd.Stderr = os.Stderr
	cmd.Start()
	err := cmd.Wait()
	writePipe.Close()
	if err != nil {
		return err
	}

	var buf bytes.Buffer
	io.Copy(&buf, readPipe)
	versions := buf.String()
	versionsArray := strings.Split(versions, "\n")
	for i := 0; i < len(versionsArray); i++ {
		trimPos := strings.LastIndex(versionsArray[i], "/") + 1
		versionsArray[i] = versionsArray[i][trimPos:]
		if strings.Contains(versionsArray[i], "^{}") ||
			(isDeprecated(versionsArray[i]) && program == "tarantool") {
			continue
		}
		os.Stdout.Write([]byte(versionsArray[i]))
		os.Stdout.Write([]byte("\n"))
	}
	os.Stdout.Write([]byte("master\n"))
	return err
}
