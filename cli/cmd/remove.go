package cmd

import (
	"fmt"
	"strings"

	"github.com/apex/log"
	"github.com/spf13/cobra"
	"github.com/tarantool/tt/cli/cmdcontext"
	"github.com/tarantool/tt/cli/configure"
	"github.com/tarantool/tt/cli/modules"
	"github.com/tarantool/tt/cli/remove"
)

// NewRemoveCmd creates remove command.
func NewRemoveCmd() *cobra.Command {
	var removeCmd = &cobra.Command{
		Use:   "remove <PROGRAM>",
		Short: "Remove tarantool/tt",
		Long: "Available programs:\n" +
			"tt - Tarantool CLI\n" +
			"tarantool - Tarantool\n" +
			"tarantool-ee - Tarantool enterprise edition\n" +
			"e.g tt=master",
		Args: cobra.ExactArgs(1),
		Run: func(cmd *cobra.Command, args []string) {
			err := modules.RunCmd(&cmdCtx, cmd.Name(), &modulesInfo, InternalRemoveModule, args)
			if err != nil {
				log.Fatalf(err.Error())
			}
		},
	}
	return removeCmd
}

// InternalRemoveModule is a default remove module.
func InternalRemoveModule(cmdCtx *cmdcontext.CmdCtx, args []string) error {
	cliOpts, err := configure.GetCliOpts(cmdCtx.Cli.ConfigPath)
	if err != nil {
		return err
	}
	if !strings.Contains(args[0], "=") {
		return fmt.Errorf("Incorrect usage.\n   e.g program=version")
	}
	err = remove.RemoveProgram(args[0], cliOpts.App.BinDir, cliOpts.App.IncludeDir, cmdCtx)
	return err
}