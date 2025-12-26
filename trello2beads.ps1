#!/usr/bin/env pwsh
# Convenience wrapper for trello2beads Python module
# Usage: .\trello2beads.ps1 [OPTIONS]

# Get the directory where this script lives
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Add the repo directory to PYTHONPATH so the module can be found
$env:PYTHONPATH = "$ScriptDir" + [IO.Path]::PathSeparator + $env:PYTHONPATH

# Run the trello2beads module with all arguments passed through
& python -m trello2beads $args
exit $LASTEXITCODE
