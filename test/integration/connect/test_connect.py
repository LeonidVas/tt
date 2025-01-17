import os
import re
import shutil
import subprocess

import psutil
import pytest

from utils import (control_socket, get_tarantool_version, kill_procs,
                   run_command_and_get_output, run_path, wait_file)

tarantool_major_version, tarantool_minor_version = get_tarantool_version()


@pytest.fixture(autouse=True)
def kill_remain_processes_wrapper(tt_cmd):
    # Run test.
    yield

    tt_proc = subprocess.Popen(
        ['pgrep', '-f', tt_cmd],
        stdout=subprocess.PIPE,
        shell=False
    )
    response = tt_proc.communicate()[0]
    procs = [psutil.Process(int(pid)) for pid in response.split()]

    kill_procs(procs)


def copy_data(dst, file_paths):
    for path in file_paths:
        shutil.copy(path, dst)


def start_app(tt_cmd, tmpdir_with_cfg, app_name):
    # Start an instance.
    start_cmd = [tt_cmd, "start", app_name]
    instance_process = subprocess.Popen(
        start_cmd,
        cwd=tmpdir_with_cfg,
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
        text=True
    )
    start_output = instance_process.stdout.readline()
    assert re.search(r"Starting an instance", start_output)


def stop_app(tt_cmd, tmpdir, app_name):
    stop_cmd = [tt_cmd, "stop", app_name]
    stop_rc, stop_out = run_command_and_get_output(stop_cmd, cwd=tmpdir)


def try_execute_on_instance(tt_cmd, tmpdir, instance,
                            file_path=None,
                            stdin=None,
                            env=None,
                            opts=None,
                            args=None):
    connect_cmd = [tt_cmd, "connect", instance]
    if file_path is not None:
        connect_cmd.append("-f")
        connect_cmd.append(file_path)

    if opts is not None:
        for k, v in opts.items():
            connect_cmd.append(k)
            connect_cmd.append(v)

    if args is not None:
        for arg in args:
            connect_cmd.append(arg)

    instance_process = subprocess.run(
        connect_cmd,
        cwd=tmpdir,
        input=stdin,
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
        text=True,
        env=env,
    )
    return instance_process.returncode == 0, instance_process.stdout


def prepare_test_app_languages(tt_cmd, tmpdir):
    lua_file = "hello.lua"
    sql_file = "hello.sql"
    # The test application file.
    test_app_path = os.path.join(os.path.dirname(__file__), "test_single_app", "test_app.lua")
    # The test file with Lua code.
    lua_file_path = os.path.join(os.path.dirname(__file__), "test_file", lua_file)
    # The test file with SQL code.
    sql_file_path = os.path.join(os.path.dirname(__file__), "test_file", sql_file)
    # Copy test data into temporary directory.
    copy_data(tmpdir, [test_app_path, lua_file_path, sql_file_path])

    # Start an instance.
    start_app(tt_cmd, tmpdir, "test_app")

    # Check for start.
    file = wait_file(os.path.join(tmpdir, "test_app"), 'configured', [])
    assert file != ""
    return "test_app", lua_file, sql_file


def get_version(tt_cmd, tmpdir):
    run_cmd = [tt_cmd, "run", "-v"]
    instance_process = subprocess.run(
        run_cmd,
        cwd=tmpdir,
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
        text=True
    )
    if instance_process.returncode == 0:
        stdout = instance_process.stdout
        full = stdout.splitlines()[0]
        for word in re.split(r'\s', full):
            matched = re.match(r'^\d+\.\d+\.\d+', word)
            if matched:
                print("Matched:")
                print(matched)
                version = re.split(r'\.', matched.group(0))
                return True, int(version[0]), int(version[1]), int(version[2])
    return False, 0, 0, 0


def is_language_supported(tt_cmd, tmpdir):
    ok, major, minor, patch = get_version(tt_cmd, tmpdir)
    assert ok
    return major >= 2


def is_tarantool_ee():
    cmd = ["tarantool", "--version"]
    instance_process = subprocess.run(
        cmd,
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
        text=True
    )
    if instance_process.returncode == 0:
        return "Tarantool Enterprise" in instance_process.stdout
    return False


def is_tarantool_major_one():
    cmd = ["tarantool", "--version"]
    instance_process = subprocess.run(
        cmd,
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
        text=True
    )
    if instance_process.returncode == 0:
        return "Tarantool 1." in instance_process.stdout
    return False


def skip_if_language_unsupported(tt_cmd, tmpdir, test_app):
    if not is_language_supported(tt_cmd, tmpdir):
        stop_app(tt_cmd, tmpdir, test_app)
        pytest.skip("\\set language is unsupported")


def skip_if_language_supported(tt_cmd, tmpdir, test_app):
    if is_language_supported(tt_cmd, tmpdir):
        stop_app(tt_cmd, tmpdir, test_app)
        pytest.skip("\\set language is supported")


def skip_if_tarantool_ce():
    if not is_tarantool_ee():
        pytest.skip("Tarantool Enterprise required")


def test_connect_and_get_commands_outputs(tt_cmd, tmpdir_with_cfg):
    tmpdir = tmpdir_with_cfg
    empty_file = "empty.lua"
    # The test application file.
    test_app_path = os.path.join(os.path.dirname(__file__), "test_localhost_app", "test_app.lua")
    # The test file.
    empty_file_path = os.path.join(os.path.dirname(__file__), "test_file", empty_file)
    # Copy test data into temporary directory.
    copy_data(tmpdir, [test_app_path, empty_file_path])

    # Start an instance.
    start_app(tt_cmd, tmpdir, "test_app")

    # Check for start.
    file = wait_file(os.path.join(tmpdir, 'test_app'), 'ready', [])
    assert file != ""

    commands = {}
    help_output = """
  To get help, see the Tarantool manual at https://tarantool.io/en/doc/
  To start the interactive Tarantool tutorial, type 'tutorial()' here.

  This help is expanded with additional backslash commands
  because tt connect is using.

  Available backslash commands:

  \\help, ?                        -- show this screen
  \\set language <language>        -- set language lua (default) or sql
  \\set output <format>            -- set format lua, table, ttable or yaml (default)
  \\set table_format <format>      -- set table format default, jira or markdown
  \\set graphics <false/true>      -- disables/enables pseudographics for table modes
  \\set table_column_width <width> -- set max column width for table/ttable
  \\xw <width>                     -- set max column width for table/ttable
  \\x                              -- switches output format cyclically
  \\x[l,t,T,y]                     -- set output format lua, table, ttable or yaml
  \\x[g,G]                         -- disables/enables pseudographics for table modes
  \\shortcuts                      -- show available hotkeys and shortcuts
  \\quit, \\q                       -- quit from the console

"""
    commands["\\help"] = help_output
    commands["?"] = help_output
    commands["\\set output lua"] = ""
    commands["\\set output table"] = ""
    commands["\\set output ttable"] = ""
    commands["\\set output yaml"] = ""
    commands["\\set table_format default"] = ""
    commands["\\set table_format jira"] = ""
    commands["\\set table_format markdown"] = ""
    commands["\\set graphics false"] = ""
    commands["\\set graphics true"] = ""
    commands["\\set table_column_width 1"] = ""
    commands["\\xw 1"] = ""
    commands["\\x"] = ""
    commands["\\xl"] = ""
    commands["\\xt"] = ""
    commands["\\xT"] = ""
    commands["\\xy"] = ""
    commands["\\xg"] = ""
    commands["\\xG"] = ""
    commands["\\shortcuts"] = """---
- - |
    Available hotkeys and shortcuts:

       Ctrl + J / Ctrl + M [Enter] -- Enter the command
       Ctrl + A [Home]             -- Go to the beginning of the command
       Ctrl + E [End]              -- Go to the end of the command
       Ctrl + P [Up Arrow]         -- Previous command
       Ctrl + N [Down Arrow]       -- Next command
       Ctrl + F [Right Arrow]      -- Forward one character
       Ctrl + B [Left Arrow]       -- Backward one character
       Ctrl + H [Backspace]        -- Delete character before the cursor
       Ctrl + I [Tab]              -- Get next completion
       BackTab                     -- Get previous completion
       Ctrl + D                    -- Delete character under the cursor
       Ctrl + W                    -- Cut the word before the cursor
       Ctrl + K                    -- Cut the command after the cursor
       Ctrl + U                    -- Cut the command before the cursor
       Ctrl + L                    -- Clear the screen
       Ctrl + R                    -- Enter in the reverse search mode
       Ctrl + C                    -- Interrupt current unfinished expression
       Alt + B                     -- Move backwards one word
       Alt + F                     -- Move forwards one word
...
"""
    commands["\\quit"] = "   • Quit from the console    \n"
    commands["\\q"] = "   • Quit from the console    \n"

    try:
        for key, value in commands.items():
            ret, output = try_execute_on_instance(tt_cmd, tmpdir, "localhost:3013", stdin=key)
            print(output)
            assert ret

            assert output == value
    finally:
        stop_app(tt_cmd, tmpdir, "test_app")


def test_connect_and_get_commands_errors(tt_cmd, tmpdir_with_cfg):
    tmpdir = tmpdir_with_cfg
    empty_file = "empty.lua"
    # The test application file.
    test_app_path = os.path.join(os.path.dirname(__file__), "test_localhost_app", "test_app.lua")
    # The test file.
    empty_file_path = os.path.join(os.path.dirname(__file__), "test_file", empty_file)
    # Copy test data into temporary directory.
    copy_data(tmpdir, [test_app_path, empty_file_path])

    # Start an instance.
    start_app(tt_cmd, tmpdir, "test_app")

    # Check for start.
    file = wait_file(os.path.join(tmpdir, 'test_app'), 'ready', [])
    assert file != ""

    commands = {}
    commands["\\help arg"] = "⨯ the command does not expect arguments"
    commands["? arg"] = "⨯ the command does not expect arguments"
    commands["\\set language"] = "⨯ the command expects one of: lua, sql"
    commands["\\set language arg"] = "⨯ the command expects one of: lua, sql"
    commands["\\set language arg arg"] = "⨯ the command expects one of: lua, sql"
    commands["\\set output"] = "⨯ the command expects one of: lua, table, ttable, yaml"
    commands["\\set output arg"] = "⨯ the command expects one of: lua, table, ttable, yaml"
    commands["\\set table_format"] = "⨯ the command expects one of: default, jira, markdown"
    commands["\\set table_format arg"] = "⨯ the command expects one of: default, jira, markdown"
    commands["\\set graphics"] = "⨯ the command expects one boolean"
    commands["\\set graphics arg"] = "⨯ the command expects one boolean"
    commands["\\set table_column_width"] = "⨯ the command expects one unsigned number"
    commands["\\set table_column_width arg"] = "⨯ the command expects one unsigned number"
    commands["\\xw"] = "⨯ the command expects one unsigned number"
    commands["\\xw arg"] = "⨯ the command expects one unsigned number"
    commands["\\x arg"] = "⨯ the command does not expect arguments"
    commands["\\xl arg"] = "⨯ the command does not expect arguments"
    commands["\\xt arg"] = "⨯ the command does not expect arguments"
    commands["\\xT arg"] = "⨯ the command does not expect arguments"
    commands["\\xy arg"] = "⨯ the command does not expect arguments"
    commands["\\xg arg"] = "⨯ the command does not expect arguments"
    commands["\\xG arg"] = "⨯ the command does not expect arguments"
    commands["\\shortcuts arg"] = "⨯ the command does not expect arguments"
    commands["\\quit arg"] = "⨯ the command does not expect arguments"
    commands["\\q arg"] = "⨯ the command does not expect arguments"

    try:
        for key, value in commands.items():
            ret, output = try_execute_on_instance(tt_cmd, tmpdir, "localhost:3013", stdin=key)
            assert ret

            assert value in output
    finally:
        stop_app(tt_cmd, tmpdir, "test_app")


def test_connect_to_localhost_app(tt_cmd, tmpdir_with_cfg):
    tmpdir = tmpdir_with_cfg
    empty_file = "empty.lua"
    # The test application file.
    test_app_path = os.path.join(os.path.dirname(__file__), "test_localhost_app", "test_app.lua")
    # The test file.
    empty_file_path = os.path.join(os.path.dirname(__file__), "test_file", empty_file)
    # Copy test data into temporary directory.
    copy_data(tmpdir, [test_app_path, empty_file_path])

    # Start an instance.
    start_app(tt_cmd, tmpdir, "test_app")

    # Check for start.
    file = wait_file(os.path.join(tmpdir, 'test_app'), 'ready', [])
    assert file != ""

    # Connect to a wrong instance.
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, "localhost:6666", empty_file)
    assert not ret
    assert re.search(r"   ⨯ unable to establish connection", output)

    # Connect to the instance.
    uris = ["localhost:3013", "tcp://localhost:3013"]
    for uri in uris:
        # Execute a script.
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri, empty_file)
        assert ret
        # Execute stdout.
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri,
                                              stdin="return ...",
                                              args=["-f-", "Hello", "World"])
        assert ret
        assert output == "---\n- Hello\n- World\n...\n\n"

        # Execute stdout without args.
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri,
                                              stdin="2+2")
        assert ret
        assert output == "---\n- 4\n...\n\n"

    # Stop the Instance.
    stop_app(tt_cmd, tmpdir, "test_app")


def test_connect_to_ssl_app(tt_cmd, tmpdir_with_cfg):
    skip_if_tarantool_ce()

    tmpdir = tmpdir_with_cfg
    empty_file = "empty.lua"
    # The test application file.
    test_app_path = os.path.join(os.path.dirname(__file__), "test_ssl_app")
    # The test file.
    empty_file_path = os.path.join(os.path.dirname(__file__), "test_file", empty_file)

    # Copy test data into temporary directory.
    shutil.copytree(test_app_path, os.path.join(tmpdir, "test_ssl_app"))
    shutil.copy(empty_file_path, os.path.join(tmpdir, "test_ssl_app", empty_file))

    # Start an instance.
    start_app(tt_cmd, tmpdir, "test_ssl_app")

    # Check for start.
    file = wait_file(os.path.join(tmpdir, 'test_ssl_app'), 'ready', [])
    assert file != ""

    server = "localhost:3013"
    # Connect without SSL options.
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, server, empty_file)
    assert not ret
    assert re.search(r"   ⨯ unable to establish connection", output)

    # Connect to the instance.
    opts = {
        "--sslkeyfile": "test_ssl_app/localhost.key",
        "--sslcertfile": "test_ssl_app/localhost.crt",
        "--sslcafile": "test_ssl_app/ca.crt",
    }
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, server, empty_file, opts=opts)
    assert ret

    # Stop the Instance.
    stop_app(tt_cmd, tmpdir, "test_ssl_app")


def test_connect_to_localhost_app_credentials(tt_cmd, tmpdir_with_cfg):
    tmpdir = tmpdir_with_cfg
    empty_file = "empty.lua"
    # The test application file.
    test_app_path = os.path.join(os.path.dirname(__file__), "test_localhost_app", "test_app.lua")
    # The test file.
    empty_file_path = os.path.join(os.path.dirname(__file__), "test_file", empty_file)
    # Copy test data into temporary directory.
    copy_data(tmpdir, [test_app_path, empty_file_path])

    # Start an instance.
    start_app(tt_cmd, tmpdir, "test_app")

    # Check for start.
    file = wait_file(os.path.join(tmpdir, 'test_app'), 'ready', [])
    assert file != ""

    # Connect with a wrong credentials.
    opts = {"-u": "test", "-p": "wrong_password"}
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, "localhost:3013", empty_file, opts=opts)
    assert not ret
    assert re.search(r"   ⨯ unable to establish connection", output)

    # Connect with a wrong credentials via URL.
    uri = "test:wrong_password@localhost:3013"
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri, empty_file)
    assert not ret
    assert re.search(r"   ⨯ unable to establish connection", output)

    # Connect with a wrong credentials via environment variables.
    env = {"TT_CLI_USERNAME": "test", "TT_CLI_PASSWORD": "wrong_password"}
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, "localhost:3013", empty_file, env=env)
    assert not ret
    assert re.search(r"   ⨯ unable to establish connection", output)

    # Connect with a valid credentials.
    opts = {"-u": "test", "-p": "password"}
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, "localhost:3013", empty_file, opts=opts)
    assert ret

    # Connect with a valid credentials via URL.
    uri = "test:password@localhost:3013"
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri, empty_file)
    assert ret

    # Connect with a valid credentials via environment variables.
    env = {"TT_CLI_USERNAME": "test", "TT_CLI_PASSWORD": "password"}
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, "localhost:3013", empty_file, env=env)
    assert ret

    # Connect with a valid credentials and wrong environment variables.
    env = {"TT_CLI_USERNAME": "test", "TT_CLI_PASSWORD": "wrong_password"}
    opts = {"-u": "test", "-p": "password"}
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, "localhost:3013",
                                          empty_file, opts=opts, env=env)
    assert ret

    # Connect with a valid credentials via URL and wrong environment variables.
    env = {"TT_CLI_USERNAME": "test", "TT_CLI_PASSWORD": "wrong_password"}
    uri = "test:password@localhost:3013"
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri, empty_file, env=env)
    assert ret

    # Connect with a valid mixes of credentials and environment variables.
    env = {"TT_CLI_PASSWORD": "password"}
    opts = {"-u": "test"}
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, "localhost:3013",
                                          empty_file, opts=opts, env=env)
    assert ret

    env = {"TT_CLI_USERNAME": "test"}
    opts = {"-p": "password"}
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, "localhost:3013",
                                          empty_file, opts=opts, env=env)
    assert ret

    # Connect with a valid credentials via flags and via URL.
    opts = {"-u": "test", "-p": "password"}
    uri = "test:password@localhost:3013"
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri, empty_file, opts=opts)
    assert not ret
    assert re.search(r"   ⨯ username and password are specified with flags and a URI", output)

    # Stop the Instance.
    stop_app(tt_cmd, tmpdir, "test_app")


def test_connect_to_single_instance_app(tt_cmd, tmpdir_with_cfg):
    tmpdir = tmpdir_with_cfg
    empty_file = "empty.lua"
    # The test application file.
    test_app_path = os.path.join(os.path.dirname(__file__), "test_single_app", "test_app.lua")
    # The test file.
    empty_file_path = os.path.join(os.path.dirname(__file__), "test_file", empty_file)
    # Copy test data into temporary directory.
    copy_data(tmpdir, [test_app_path, empty_file_path])

    # Start an instance.
    start_app(tt_cmd, tmpdir, "test_app")

    # Check for start.
    file = wait_file(os.path.join(tmpdir, "test_app", run_path, "test_app"),
                     control_socket, [])
    assert file != ""

    # Connect to a wrong instance.
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, "any_app", empty_file)
    assert not ret
    assert re.search(r"   ⨯ can\'t collect instance information for any_app", output)

    # Connect to the instance and execute a script.
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, "test_app", empty_file)
    assert ret

    # Connect to the instance and execute stdout.
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, "test_app",
                                          stdin="return ...",
                                          args=["-f-", "Hello", "World"])
    print(output)
    assert ret
    assert output == "---\n- Hello\n- World\n...\n\n"

    # Stop the Instance.
    stop_app(tt_cmd, tmpdir, "test_app")


def test_connect_to_single_instance_app_credentials(tt_cmd, tmpdir_with_cfg):
    tmpdir = tmpdir_with_cfg
    empty_file = "empty.lua"
    # The test application file.
    test_app_path = os.path.join(os.path.dirname(__file__), "test_single_app", "test_app.lua")
    # The test file.
    empty_file_path = os.path.join(os.path.dirname(__file__), "test_file", empty_file)
    # Copy test data into temporary directory.
    copy_data(tmpdir, [test_app_path, empty_file_path])

    # Start an instance.
    start_app(tt_cmd, tmpdir, "test_app")

    # Check for start.
    file = wait_file(os.path.join(tmpdir, "test_app", run_path, "test_app"),
                     control_socket, [])
    assert file != ""

    # Connect with a wrong credentials.
    opts = {"-u": "test", "-p": "wrong_password"}
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, "test_app", empty_file, opts=opts)
    assert not ret
    assert re.search(r"   ⨯ username and password are not supported with a" +
                     " connection via a control socket", output)

    # Connect with a valid credentials.
    opts = {"-u": "test", "-p": "password"}
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, "test_app", empty_file, opts=opts)
    assert not ret
    assert re.search(r"   ⨯ username and password are not supported with a" +
                     " connection via a control socket", output)

    # Connect with environment variables.
    env = {"TT_CLI_USERNAME": "test", "TT_CLI_PASSWORD": "wrong_password"}
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, "test_app", empty_file, env=env)
    assert ret

    # Stop the Instance.
    stop_app(tt_cmd, tmpdir, "test_app")


def test_connect_to_multi_instances_app(tt_cmd, tmpdir_with_cfg):
    tmpdir = tmpdir_with_cfg
    instances = ['master', 'replica', 'router']
    app_name = "test_multi_app"
    empty_file = "empty.lua"
    # Copy the test application to the "run" directory.
    test_app_path = os.path.join(os.path.dirname(__file__), app_name)
    tmp_app_path = os.path.join(tmpdir, app_name)
    shutil.copytree(test_app_path, tmp_app_path)
    # The test file.
    empty_file_path = os.path.join(os.path.dirname(__file__), "test_file", empty_file)
    # Copy test data into temporary directory.
    copy_data(tmpdir, [empty_file_path])

    # Start instances.
    start_app(tt_cmd, tmpdir, app_name)

    # Check for start.
    for instance in instances:
        master_run_path = os.path.join(tmpdir, app_name, run_path, instance)
        file = wait_file(master_run_path, control_socket, [])
        assert file != ""

    # Connect to a non-exist instance.
    non_exist = app_name + ":" + "any_name"
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, non_exist, empty_file)
    assert not ret
    assert re.search(rf"   ⨯ can't collect instance information for {non_exist}", output)

    # Connect to instances.
    for instance in instances:
        full_name = app_name + ":" + instance
        ret, _ = try_execute_on_instance(tt_cmd, tmpdir, full_name, empty_file)
        assert ret

    # Stop the Instance.
    stop_app(tt_cmd, tmpdir, app_name)


def test_connect_to_multi_instances_app_credentials(tt_cmd, tmpdir_with_cfg):
    tmpdir = tmpdir_with_cfg
    app_name = "test_multi_app"
    empty_file = "empty.lua"
    # Copy the test application to the "run" directory.
    test_app_path = os.path.join(os.path.dirname(__file__), app_name)
    tmp_app_path = os.path.join(tmpdir, app_name)
    shutil.copytree(test_app_path, tmp_app_path)
    # The test file.
    empty_file_path = os.path.join(os.path.dirname(__file__), "test_file", empty_file)
    # Copy test data into temporary directory.
    copy_data(tmpdir, [empty_file_path])

    # Start instances.
    start_app(tt_cmd, tmpdir, app_name)

    # Check for start.
    master_run_path = os.path.join(tmpdir, app_name, run_path, "master")
    file = wait_file(master_run_path, control_socket, [])
    assert file != ""

    # Connect with a wrong credentials.
    full_name = app_name + ":master"
    opts = {"-u": "test", "-p": "wrong_password"}
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, full_name, empty_file, opts=opts)
    assert not ret
    assert re.search(r"   ⨯ username and password are not supported with a" +
                     " connection via a control socket", output)

    # Connect with a valid credentials.
    full_name = app_name + ":master"
    opts = {"-u": "test", "-p": "password"}
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, full_name, empty_file, opts=opts)
    assert not ret
    assert re.search(r"   ⨯ username and password are not supported with a" +
                     " connection via a control socket", output)

    # Connect with environment variables.
    env = {"TT_CLI_USERNAME": "test", "TT_CLI_PASSWORD": "wrong_password"}
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, full_name, empty_file, env=env)
    assert ret

    # Stop the Instance.
    stop_app(tt_cmd, tmpdir, app_name)


def test_connect_language_default_lua(tt_cmd, tmpdir_with_cfg):
    tmpdir = tmpdir_with_cfg
    test_app, lua_file, sql_file = prepare_test_app_languages(tt_cmd, tmpdir)

    # Execute Lua-code.
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, test_app, lua_file)
    assert ret
    assert re.search(r"Hello, world", output)

    # Execute SQL-code.
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, test_app, sql_file)
    assert ret
    assert re.search(r"metadata:", output) is None

    # Stop the Instance.
    stop_app(tt_cmd, tmpdir, test_app)


def test_connect_language_lua(tt_cmd, tmpdir_with_cfg):
    tmpdir = tmpdir_with_cfg
    test_app, lua_file, sql_file = prepare_test_app_languages(tt_cmd, tmpdir)

    skip_if_language_unsupported(tt_cmd, tmpdir, test_app)

    # Execute Lua-code.
    opts = {"-l": "lua"}
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, test_app, lua_file, opts=opts)
    assert ret
    assert re.search(r"Hello, world", output)

    # Execute SQL-code.
    for lang in ["lua", "LuA", "LUA"]:
        opts = {"-l": lang}
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, test_app, sql_file, opts=opts)
        assert ret
        assert re.search(r"metadata:", output) is None

    # Stop the Instance.
    stop_app(tt_cmd, tmpdir, test_app)


def test_connect_language_sql(tt_cmd, tmpdir_with_cfg):
    tmpdir = tmpdir_with_cfg
    test_app, lua_file, sql_file = prepare_test_app_languages(tt_cmd, tmpdir)

    skip_if_language_unsupported(tt_cmd, tmpdir, test_app)

    # Execute Lua-code.
    opts = {"-l": "sql"}
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, test_app, lua_file, opts=opts)
    assert ret
    assert re.search(r"Hello, world", output) is None

    # Execute SQL-code.
    for lang in ["sql", "SqL", "SQL"]:
        opts = {"-l": lang}
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, test_app, sql_file, opts=opts)
        assert ret
        assert re.search(r"metadata:", output)

    # Stop the Instance.
    stop_app(tt_cmd, tmpdir, test_app)


def test_connect_language_l_equal_language(tt_cmd, tmpdir_with_cfg):
    tmpdir = tmpdir_with_cfg
    test_app, lua_file, sql_file = prepare_test_app_languages(tt_cmd, tmpdir)

    skip_if_language_unsupported(tt_cmd, tmpdir, test_app)

    for opt in ["-l", "--language"]:
        # Execute Lua-code.
        opts = {opt: "sql"}
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, test_app, lua_file, opts=opts)
        assert ret
        assert re.search(r"Hello, world", output) is None

        # Execute SQL-code.
        opts = {opt: "sql"}
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, test_app, sql_file, opts=opts)
        assert ret
        assert re.search(r"metadata:", output)

    # Stop the Instance.
    stop_app(tt_cmd, tmpdir, test_app)


def test_connect_language_invalid(tt_cmd, tmpdir_with_cfg):
    tmpdir = tmpdir_with_cfg
    test_app, lua_file, sql_file = prepare_test_app_languages(tt_cmd, tmpdir)

    # Execute Lua-code.
    opts = {"-l": "invalid"}
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, test_app, lua_file, opts=opts)
    assert not ret
    assert re.search(r"   ⨯ unsupported language: invalid", output)

    # Execute SQL-code.
    opts = {"-l": "invalid"}
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, test_app, sql_file, opts=opts)
    assert not ret
    assert re.search(r"   ⨯ unsupported language: invalid", output)

    # Stop the Instance.
    stop_app(tt_cmd, tmpdir, test_app)


def test_connect_language_set_if_unsupported(tt_cmd, tmpdir_with_cfg):
    tmpdir = tmpdir_with_cfg
    test_app, lua_file, sql_file = prepare_test_app_languages(tt_cmd, tmpdir)

    skip_if_language_supported(tt_cmd, tmpdir, test_app)

    # Execute Lua-code.
    opts = {"-l": "lua"}
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, test_app, lua_file, opts=opts)
    assert not ret
    assert re.search(r"   ⨯ unable to change a language: unexpected response:", output)

    # Execute SQL-code.
    opts = {"-l": "sql"}
    ret, output = try_execute_on_instance(tt_cmd, tmpdir, test_app, sql_file, opts=opts)
    assert not ret
    assert re.search(r"   ⨯ unable to change a language: unexpected response:", output)

    # Stop the Instance.
    stop_app(tt_cmd, tmpdir, test_app)


def test_output_format_lua(tt_cmd, tmpdir_with_cfg):
    tmpdir = tmpdir_with_cfg
    # The test application file.
    test_app_path = os.path.join(os.path.dirname(__file__), "test_output_format_app",
                                                            "test_app.lua")
    # Copy test data into temporary directory.
    copy_data(tmpdir, [test_app_path])

    # Start an instance.
    start_app(tt_cmd, tmpdir, "test_app")

    # Check for start.
    file = wait_file(os.path.join(tmpdir, 'test_app'), 'ready', [])
    assert file != ""

    # Connect to the instance.
    uris = ["localhost:3013", "tcp://localhost:3013"]
    for uri in uris:
        # Execute stdin.
        ret, output = try_execute_on_instance(
            tt_cmd, tmpdir, uri,
            stdin="2+2",
            opts={'-x': 'lua'}
        )
        assert ret
        assert output == "4;\n"

        # Execute stdin.
        ret, output = try_execute_on_instance(
            tt_cmd, tmpdir, uri,
            stdin="\n",
            opts={'-x': 'lua'}
        )
        assert ret
        assert output == ";\n"

        # Execute stdin.
        ret, output = try_execute_on_instance(
            tt_cmd, tmpdir, uri,
            stdin="1,2,3",
            opts={'-x': 'lua'}
        )
        assert ret
        assert output == "1, 2, 3;\n"

        # Execute stdin.
        ret, output = try_execute_on_instance(
            tt_cmd, tmpdir, uri,
            stdin="1,\"2\",3",
            opts={'-x': 'lua'}
        )
        assert ret
        assert output == "1, \"2\", 3;\n"

        # Execute stdin.
        ret, output = try_execute_on_instance(
            tt_cmd, tmpdir, uri,
            stdin="{1, 2,   3}",
            opts={'-x': 'lua'}
        )
        assert ret
        assert output == "{1, 2, 3};\n"

        # Execute stdin.
        ret, output = try_execute_on_instance(
            tt_cmd, tmpdir, uri,
            stdin='{10,20,box.NULL,30},{},{box.NULL},{data="hello world"}',
            opts={'-x': 'lua'}
        )
        assert ret
        assert output == '{10, 20, nil, 30}, {}, {nil}, {data = "hello world"};\n'

        # Execute stdin.
        ret, output = try_execute_on_instance(
            tt_cmd, tmpdir, uri,
            stdin='error("test")',
            opts={'-x': 'lua'}
        )
        assert ret
        assert output == '{error = "test"};\n'

    # Stop the Instance.
    stop_app(tt_cmd, tmpdir, "test_app")


def test_table_output_format(tt_cmd, tmpdir_with_cfg):
    tmpdir = tmpdir_with_cfg
    # The test application file.
    test_app_path = os.path.join(os.path.dirname(__file__), "test_output_format_app",
                                                            "test_app.lua")
    # Copy test data into temporary directory.
    copy_data(tmpdir, [test_app_path])

    # Start an instance.
    start_app(tt_cmd, tmpdir, "test_app")

    # Check for start.
    file = wait_file(os.path.join(tmpdir, 'test_app'), 'ready', [])
    assert file != ""

    # Connect to the instance.
    uris = ["localhost:3013", "tcp://localhost:3013"]
    for uri in uris:
        # Execute stdin.
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri,
                                              stdin="2+2", opts={'-x': 'table'})
        assert ret
        assert output == ("+------+\n"
                          "| col1 |\n"
                          "+------+\n"
                          "| 4    |\n"
                          "+------+\n")

        # Execute stdin.
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri,
                                              stdin="1,2,3", opts={'-x': 'table'})
        assert ret
        assert output == ("+------+\n"
                          "| col1 |\n"
                          "+------+\n"
                          "| 1    |\n"
                          "+------+\n"
                          "| 2    |\n"
                          "+------+\n"
                          "| 3    |\n"
                          "+------+\n")

        # Execute stdin.
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri,
                                              stdin="{1,2,3}", opts={'-x': 'table'})
        assert ret
        assert output == ("+------+------+------+\n"
                          "| col1 | col2 | col3 |\n"
                          "+------+------+------+\n"
                          "| 1    | 2    | 3    |\n"
                          "+------+------+------+\n")

        # Execute stdin.
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri,
                                              stdin="{10,20,30},{40,50,60},{70,80},{box.NULL,90}",
                                              opts={'-x': 'table'})
        assert ret
        assert output == ("+------+------+------+\n"
                          "| col1 | col2 | col3 |\n"
                          "+------+------+------+\n"
                          "| 10   | 20   | 30   |\n"
                          "+------+------+------+\n"
                          "| 40   | 50   | 60   |\n"
                          "+------+------+------+\n"
                          "| 70   | 80   |      |\n"
                          "+------+------+------+\n"
                          "| nil  | 90   |      |\n"
                          "+------+------+------+\n")

        # Execute stdin.
        ret, output = try_execute_on_instance(
            tt_cmd, tmpdir, uri,
            stdin="box.tuple.new({1,100,'Mike',{data=123,'test'},{10,20}})",
            opts={'-x': 'table'})
        assert ret
        assert output == ('+------+------+------+-------------------------+---------+\n'
                          '| col1 | col2 | col3 | col4                    | col5    |\n'
                          '+------+------+------+-------------------------+---------+\n'
                          '| 1    | 100  | Mike | {"1":"test","data":123} | [10,20] |\n'
                          '+------+------+------+-------------------------+---------+\n')

        # Execute stdin.
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri,
                                              stdin="{ {10,20},{30,40} }", opts={'-x': 'table'})
        assert ret
        assert output == ("+------+------+\n"
                          "| col1 | col2 |\n"
                          "+------+------+\n"
                          "| 10   | 20   |\n"
                          "+------+------+\n"
                          "| 30   | 40   |\n"
                          "+------+------+\n")

        # Execute stdin.
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri,
                                              stdin="{10,20},{30,40}", opts={'-x': 'table'})
        assert ret
        assert output == ("+------+------+\n"
                          "| col1 | col2 |\n"
                          "+------+------+\n"
                          "| 10   | 20   |\n"
                          "+------+------+\n"
                          "| 30   | 40   |\n"
                          "+------+------+\n")

        # Execute stdin.
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri,
                                              stdin="box.space.customers:select()",
                                              opts={'-x': 'table'})
        assert ret
        assert output == ("+------+-----------+------+\n"
                          "| col1 | col2      | col3 |\n"
                          "+------+-----------+------+\n"
                          "| 1    | Elizabeth | 12   |\n"
                          "+------+-----------+------+\n"
                          "| 2    | Mary      | 46   |\n"
                          "+------+-----------+------+\n"
                          "| 3    | David     | 33   |\n"
                          "+------+-----------+------+\n"
                          "| 4    | William   | 81   |\n"
                          "+------+-----------+------+\n"
                          "| 5    | Jack      | 35   |\n"
                          "+------+-----------+------+\n"
                          "| 6    | William   | 25   |\n"
                          "+------+-----------+------+\n"
                          "| 7    | Elizabeth | 18   |\n"
                          "+------+-----------+------+\n")

        # Execute stdin.
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri,
                                              stdin="{ {10,20},{30,40},true }",
                                              opts={'-x': 'table'})
        assert ret
        assert output == ("+---------+---------+------+\n"
                          "| col1    | col2    | col3 |\n"
                          "+---------+---------+------+\n"
                          "| [10,20] | [30,40] | true |\n"
                          "+---------+---------+------+\n")

        # Execute stdin.
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri,
                                              stdin="{10,20},{30,40},true",
                                              opts={'-x': 'table'})
        assert ret
        assert output == ("+------+------+\n"
                          "| col1 | col2 |\n"
                          "+------+------+\n"
                          "| 10   | 20   |\n"
                          "+------+------+\n"
                          "| 30   | 40   |\n"
                          "+------+------+\n"
                          "+------+\n"
                          "| col1 |\n"
                          "+------+\n"
                          "| true |\n"
                          "+------+\n")

        # Execute stdin.
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri,
                                              stdin="{data=123,'Hi'},{data=321,'My'},{qwe=11}",
                                              opts={'-x': 'table'})
        assert ret
        assert output == ("+------+------+\n"
                          "| col1 | data |\n"
                          "+------+------+\n"
                          "| Hi   | 123  |\n"
                          "+------+------+\n"
                          "| My   | 321  |\n"
                          "+------+------+\n"
                          "+-----+\n"
                          "| qwe |\n"
                          "+-----+\n"
                          "| 11  |\n"
                          "+-----+\n")

        # Execute stdin.
        ret, output = try_execute_on_instance(
            tt_cmd, tmpdir, uri,
            stdin="{data=123,'Hi'}, {data=321,'My'}," +
            "{qwe=11}, true, box.NULL, 2023, false, {10,20}, {30,40}, {50}",
            opts={'-x': 'table'})
        assert ret
        assert output == ("+------+------+\n"
                          "| col1 | data |\n"
                          "+------+------+\n"
                          "| Hi   | 123  |\n"
                          "+------+------+\n"
                          "| My   | 321  |\n"
                          "+------+------+\n"
                          "+-----+\n"
                          "| qwe |\n"
                          "+-----+\n"
                          "| 11  |\n"
                          "+-----+\n"
                          "+-------+\n"
                          "| col1  |\n"
                          "+-------+\n"
                          "| true  |\n"
                          "+-------+\n"
                          "| nil   |\n"
                          "+-------+\n"
                          "| 2023  |\n"
                          "+-------+\n"
                          "| false |\n"
                          "+-------+\n"
                          "+------+------+\n"
                          "| col1 | col2 |\n"
                          "+------+------+\n"
                          "| 10   | 20   |\n"
                          "+------+------+\n"
                          "| 30   | 40   |\n"
                          "+------+------+\n"
                          "| 50   |      |\n"
                          "+------+------+\n")

        if not is_tarantool_major_one():
            # Execute stdin.
            ret, output = try_execute_on_instance(
                tt_cmd, tmpdir, uri,
                stdin="box.execute('select 1 as foo, 30, 50, 4+4 as data')",
                opts={'-x': 'table'})
            assert ret
            assert output == ("+----------+----------+------+-----+\n"
                              "| COLUMN_1 | COLUMN_2 | DATA | FOO |\n"
                              "+----------+----------+------+-----+\n"
                              "| 30       | 50       | 8    | 1   |\n"
                              "+----------+----------+------+-----+\n")

            # Execute stdin.
            if (tarantool_major_version >= 3 or
               (tarantool_major_version == 2 and tarantool_minor_version >= 11)):
                select = "select * from seqscan table1"
            else:
                select = "select * from table1"

            ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri,
                                                  stdin=f"box.execute('{select}')",
                                                  opts={'-x': 'table'})
            assert ret
            assert output == ("+---------+-------------------+\n"
                              "| COLUMN1 | COLUMN2           |\n"
                              "+---------+-------------------+\n"
                              "| 10      | Hello SQL world!  |\n"
                              "+---------+-------------------+\n"
                              "| 20      | Hello LUA world!  |\n"
                              "+---------+-------------------+\n"
                              "| 30      | Hello YAML world! |\n"
                              "+---------+-------------------+\n")

        # Execute stdin.
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri,
                                              stdin="error('test')", opts={'-x': 'table'})
        assert ret
        assert output == ("+-------+\n"
                          "| error |\n"
                          "+-------+\n"
                          "| test  |\n"
                          "+-------+\n")

        # Execute stdin.
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri,
                                              stdin=" ", opts={'-x': 'table'})
        assert ret
        assert output == ("+------+\n"
                          "| col1 |\n"
                          "+------+\n"
                          "|      |\n"
                          "+------+\n")

        # Execute stdin.
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri,
                                              stdin="nil", opts={'-x': 'table'})
        assert ret
        assert output == ("+------+\n"
                          "| col1 |\n"
                          "+------+\n"
                          "| nil  |\n"
                          "+------+\n")

        # Execute stdin.
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri,
                                              stdin="{{{2+2}}}", opts={'-x': 'table'})
        assert ret
        assert output == ("+------+\n"
                          "| col1 |\n"
                          "+------+\n"
                          "| [4]  |\n"
                          "+------+\n")

        # Execute stdin.
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri,
                                              stdin="{{{{2+2}}}}", opts={'-x': 'table'})
        assert ret
        assert output == ("+-------+\n"
                          "| col1  |\n"
                          "+-------+\n"
                          "| [[4]] |\n"
                          "+-------+\n")

    # Stop the Instance.
    stop_app(tt_cmd, tmpdir, "test_app")


def test_ttable_output_format(tt_cmd, tmpdir_with_cfg):
    tmpdir = tmpdir_with_cfg
    # The test application file.
    test_app_path = os.path.join(os.path.dirname(__file__), "test_output_format_app",
                                                            "test_app.lua")
    # Copy test data into temporary directory.
    copy_data(tmpdir, [test_app_path])

    # Start an instance.
    print("\n\n")
    print(tt_cmd)
    print("\n\n")
    start_app(tt_cmd, tmpdir, "test_app")

    # Check for start.
    file = wait_file(os.path.join(tmpdir, 'test_app'), 'ready', [])
    assert file != ""

    # Connect to the instance.
    uris = ["localhost:3013", "tcp://localhost:3013"]
    for uri in uris:
        # Execute stdin.
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri,
                                              stdin="2+2", opts={'-x': 'ttable'})
        assert ret
        assert output == ("+------+---+\n"
                          "| col1 | 4 |\n"
                          "+------+---+\n")

        # Execute stdin.
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri,
                                              stdin="1,2,3", opts={'-x': 'ttable'})
        assert ret
        assert output == ("+------+---+---+---+\n"
                          "| col1 | 1 | 2 | 3 |\n"
                          "+------+---+---+---+\n")

        # Execute stdin.
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri,
                                              stdin="{10,20,30},{40,50,60},{70,80},{box.NULL,90}",
                                              opts={'-x': 'ttable'})
        assert ret
        assert output == ("+------+----+----+----+-----+\n"
                          "| col1 | 10 | 40 | 70 | nil |\n"
                          "+------+----+----+----+-----+\n"
                          "| col2 | 20 | 50 | 80 | 90  |\n"
                          "+------+----+----+----+-----+\n"
                          "| col3 | 30 | 60 |    |     |\n"
                          "+------+----+----+----+-----+\n")

        # Execute stdin.
        ret, output = try_execute_on_instance(
            tt_cmd, tmpdir, uri,
            stdin="{data=123,'Hi'},{data=321,'My'}," +
            "{qwe=11},true,box.NULL,2023,false,{10,20},{30,40},{50}",
            opts={'-x': 'ttable'})
        assert ret
        assert output == ("+------+-----+-----+\n"
                          "| col1 | Hi  | My  |\n"
                          "+------+-----+-----+\n"
                          "| data | 123 | 321 |\n"
                          "+------+-----+-----+\n"
                          "+-----+----+\n"
                          "| qwe | 11 |\n"
                          "+-----+----+\n"
                          "+------+------+-----+------+-------+\n"
                          "| col1 | true | nil | 2023 | false |\n"
                          "+------+------+-----+------+-------+\n"
                          "+------+----+----+----+\n"
                          "| col1 | 10 | 30 | 50 |\n"
                          "+------+----+----+----+\n"
                          "| col2 | 20 | 40 |    |\n"
                          "+------+----+----+----+\n")

    # Stop the Instance.
    stop_app(tt_cmd, tmpdir, "test_app")


def test_output_format_round_switching(tt_cmd, tmpdir_with_cfg):
    tmpdir = tmpdir_with_cfg
    # The test application file.
    test_app_path = os.path.join(os.path.dirname(__file__), "test_output_format_app",
                                                            "test_app.lua")
    # Copy test data into temporary directory.
    copy_data(tmpdir, [test_app_path])

    # Start an instance.
    start_app(tt_cmd, tmpdir, "test_app")

    # Check for start.
    file = wait_file(os.path.join(tmpdir, 'test_app'), 'ready', [])
    assert file != ""

    # Connect to the instance.
    uris = ["localhost:3013", "tcp://localhost:3013"]
    for uri in uris:
        # Execute stdin.
        ret, output = try_execute_on_instance(tt_cmd, tmpdir, uri,
                                              stdin="\n \\x \n\n \\x \n\n \\x \n\n \\x \n\n")
        assert ret
        assert output == ("---\n"
                          "...\n"
                          "\n"
                          ";\n"
                          "+------+\n"
                          "| col1 |\n"
                          "+------+\n"
                          "|      |\n"
                          "+------+\n"
                          "+------+--+\n"
                          "| col1 |  |\n"
                          "+------+--+\n"
                          "---\n"
                          "...\n"
                          "\n")

    # Stop the Instance.
    stop_app(tt_cmd, tmpdir, "test_app")


def test_output_format_short_named_selecting(tt_cmd, tmpdir_with_cfg):
    tmpdir = tmpdir_with_cfg
    # The test application file.
    test_app_path = os.path.join(os.path.dirname(__file__), "test_output_format_app",
                                                            "test_app.lua")
    # Copy test data into temporary directory.
    copy_data(tmpdir, [test_app_path])

    # Start an instance.
    start_app(tt_cmd, tmpdir, "test_app")

    # Check for start.
    file = wait_file(os.path.join(tmpdir, 'test_app'), 'ready', [])
    assert file != ""

    # Connect to the instance.
    uris = ["localhost:3013", "tcp://localhost:3013"]
    for uri in uris:
        # Execute stdin.
        ret, output = try_execute_on_instance(
            tt_cmd, tmpdir, uri,
            stdin="\n \\xl \n\n \\xt \n\n \\xT \n\n \\xy \n\n")
        assert ret
        assert output == ("---\n"
                          "...\n"
                          "\n"
                          ";\n"
                          "+------+\n"
                          "| col1 |\n"
                          "+------+\n"
                          "|      |\n"
                          "+------+\n"
                          "+------+--+\n"
                          "| col1 |  |\n"
                          "+------+--+\n"
                          "---\n"
                          "...\n"
                          "\n")

    # Stop the Instance.
    stop_app(tt_cmd, tmpdir, "test_app")


def test_output_format_full_named_selecting(tt_cmd, tmpdir_with_cfg):
    tmpdir = tmpdir_with_cfg
    # The test application file.
    test_app_path = os.path.join(os.path.dirname(__file__), "test_output_format_app",
                                                            "test_app.lua")
    # Copy test data into temporary directory.
    copy_data(tmpdir, [test_app_path])

    # Start an instance.
    start_app(tt_cmd, tmpdir, "test_app")

    # Check for start.
    file = wait_file(os.path.join(tmpdir, 'test_app'), 'ready', [])
    assert file != ""

    # Connect to the instance.
    uris = ["localhost:3013", "tcp://localhost:3013"]
    for uri in uris:
        # Execute stdin.
        ret, output = try_execute_on_instance(
            tt_cmd, tmpdir, uri,
            stdin=("\n \\set output lua \n\n \\set output table \n\n"
                   " \\set output ttable \n\n \\set output yaml \n\n"
                   "\\set output \n"))
        assert ret
        assert output == ("---\n"
                          "...\n"
                          "\n"
                          ";\n"
                          "+------+\n"
                          "| col1 |\n"
                          "+------+\n"
                          "|      |\n"
                          "+------+\n"
                          "+------+--+\n"
                          "| col1 |  |\n"
                          "+------+--+\n"
                          "---\n"
                          "...\n"
                          "\n"
                          "   ⨯ the command expects one of: lua, table, ttable, yaml\n"
                          "\n")

    # Stop the Instance.
    stop_app(tt_cmd, tmpdir, "test_app")


def test_output_format_tables_pseudo_graphic_disable(tt_cmd, tmpdir_with_cfg):
    tmpdir = tmpdir_with_cfg
    # The test application file.
    test_app_path = os.path.join(os.path.dirname(__file__), "test_output_format_app",
                                                            "test_app.lua")
    # Copy test data into temporary directory.
    copy_data(tmpdir, [test_app_path])

    # Start an instance.
    start_app(tt_cmd, tmpdir, "test_app")

    # Check for start.
    file = wait_file(os.path.join(tmpdir, 'test_app'), 'ready', [])
    assert file != ""

    # Connect to the instance.
    uris = ["localhost:3013", "tcp://localhost:3013"]
    for uri in uris:
        # Execute stdin.
        ret, output = try_execute_on_instance(
            tt_cmd, tmpdir, uri,
            stdin=("\\xg \n \\xt \n \\xg \n"
                   "{10,20,30}, {40,50,60}, {70, 80}, {box.NULL, 1000000000} \n"
                   "\\xT \n"
                   "{10,20,30}, {40,50,60}, {70, 80}, {box.NULL, 1000000000} \n"
                   "\\xG \n\n")
                   )
        assert ret
        assert output == (" col1  col2        col3 \n"
                          " 10    20          30   \n"
                          " 40    50          60   \n"
                          " 70    80               \n"
                          " nil   1000000000       \n"
                          "\n"
                          " col1  10  40  70  nil        \n"
                          " col2  20  50  80  1000000000 \n"
                          " col3  30  60                 \n"
                          "\n"
                          "+------+--+\n"
                          "| col1 |  |\n"
                          "+------+--+\n")

    # Stop the Instance.
    stop_app(tt_cmd, tmpdir, "test_app")


def test_output_format_tables_width_option(tt_cmd, tmpdir_with_cfg):
    tmpdir = tmpdir_with_cfg
    # The test application file.
    test_app_path = os.path.join(os.path.dirname(__file__), "test_output_format_app",
                                                            "test_app.lua")
    # Copy test data into temporary directory.
    copy_data(tmpdir, [test_app_path])

    # Start an instance.
    start_app(tt_cmd, tmpdir, "test_app")

    # Check for start.
    file = wait_file(os.path.join(tmpdir, 'test_app'), 'ready', [])
    assert file != ""

    # Connect to the instance.
    uris = ["localhost:3013", "tcp://localhost:3013"]
    for uri in uris:
        # Execute stdin.
        ret, output = try_execute_on_instance(
            tt_cmd, tmpdir, uri,
            stdin=(
                '\\set table_column_width 0 \n'
                '{"1234567890","123456","12345","1234"},{"1234567890","123456","12345","1234"}\n'
                '\\xw 5 \n'
                '{"1234567890","123456","12345","1234"},{"1234567890","123456","12345","1234"}\n'
                '\\xT \n'
                '{"1234567890","123456","12345","1234"},{"1234567890","123456","12345","1234"}\n'
                '\\xw -1\n'
                '\\xy \n'
                '\\set table_column_width 10 \n'
                ), opts={'-x': 'table'}
            )
        assert ret
        print(output)
        assert output == ("+------------+--------+-------+------+\n"
                          "| col1       | col2   | col3  | col4 |\n"
                          "+------------+--------+-------+------+\n"
                          "| 1234567890 | 123456 | 12345 | 1234 |\n"
                          "+------------+--------+-------+------+\n"
                          "| 1234567890 | 123456 | 12345 | 1234 |\n"
                          "+------------+--------+-------+------+\n"
                          "+-------+-------+-------+------+\n"
                          "| col1  | col2  | col3  | col4 |\n"
                          "+-------+-------+-------+------+\n"
                          "| 12345 | 12345 | 12345 | 1234 |\n"
                          "| +6789 | +6    |       |      |\n"
                          "| +0    |       |       |      |\n"
                          "+-------+-------+-------+------+\n"
                          "| 12345 | 12345 | 12345 | 1234 |\n"
                          "| +6789 | +6    |       |      |\n"
                          "| +0    |       |       |      |\n"
                          "+-------+-------+-------+------+\n"
                          "+------+-------+-------+\n"
                          "| col1 | 12345 | 12345 |\n"
                          "|      | +6789 | +6789 |\n"
                          "|      | +0    | +0    |\n"
                          "+------+-------+-------+\n"
                          "| col2 | 12345 | 12345 |\n"
                          "|      | +6    | +6    |\n"
                          "+------+-------+-------+\n"
                          "| col3 | 12345 | 12345 |\n"
                          "+------+-------+-------+\n"
                          "| col4 | 1234  | 1234  |\n"
                          "+------+-------+-------+\n"
                          "   ⨯ the command expects one unsigned number\n"
                          "\n")

    # Stop the Instance.
    stop_app(tt_cmd, tmpdir, "test_app")


def test_output_format_tables_dialects(tt_cmd, tmpdir_with_cfg):
    tmpdir = tmpdir_with_cfg
    # The test application file.
    test_app_path = os.path.join(os.path.dirname(__file__), "test_output_format_app",
                                                            "test_app.lua")
    # Copy test data into temporary directory.
    copy_data(tmpdir, [test_app_path])

    # Start an instance.
    start_app(tt_cmd, tmpdir, "test_app")

    # Check for start.
    file = wait_file(os.path.join(tmpdir, 'test_app'), 'ready', [])
    assert file != ""

    # Connect to the instance.
    uris = ["localhost:3013"]
    for uri in uris:
        # Connect to the instance.
        uris = ["localhost:3013", "tcp://localhost:3013"]
        for uri in uris:
            # Execute stdin.
            ret, output = try_execute_on_instance(
                tt_cmd, tmpdir, uri,
                stdin=('\\xw 5 \n \\set table_format markdown \n'
                       '{10,20,30}, {40,50,60}, {70, 80}, {box.NULL, 1000000000}\n'
                       '\\xw 0 \n'
                       '\\xT \n'
                       '{10,20,30}, {40,50,60}, {70, 80}, {box.NULL, 1000000000}\n'
                       '\\set table_format jira \n'
                       '{10,20,30}, {40,50,60}, {70, 80}, {box.NULL, 1000000000}\n'
                       '\\xt \n'
                       '{10,20,30}, {40,50,60}, {70, 80}, {box.NULL, 1000000000}\n'
                       '\\xy \n'
                       '\\set table_format jira \n'
                       ), opts={'-x': 'table'}
                )
            assert ret
            print(output)
            assert output == ("| | | |\n"
                              "|-|-|-|\n"
                              "| col1 | col2 | col3 |\n"
                              "| 10 | 20 | 30 |\n"
                              "| 40 | 50 | 60 |\n"
                              "| 70 | 80 |  |\n"
                              "| nil | 10000+0000+0 |  |\n"
                              "\n"
                              "| | | | | |\n"
                              "|-|-|-|-|-|\n"
                              "| col1 | 10 | 40 | 70 | nil |\n"
                              "| col2 | 20 | 50 | 80 | 1000000000 |\n"
                              "| col3 | 30 | 60 |  |  |\n"
                              "\n"
                              "| col1 | 10 | 40 | 70 | nil |\n"
                              "| col2 | 20 | 50 | 80 | 1000000000 |\n"
                              "| col3 | 30 | 60 |  |  |\n"
                              "\n"
                              "| col1 | col2 | col3 |\n"
                              "| 10 | 20 | 30 |\n"
                              "| 40 | 50 | 60 |\n"
                              "| 70 | 80 |  |\n"
                              "| nil | 1000000000 |  |\n"
                              "\n")

    # Stop the Instance.
    stop_app(tt_cmd, tmpdir, "test_app")
