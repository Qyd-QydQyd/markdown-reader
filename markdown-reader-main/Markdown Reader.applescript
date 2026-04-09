use scripting additions

on run
    set scriptDir to POSIX path of ((container of (path to me)) as alias)
    do shell script "open -a Terminal " & quoted form of (scriptDir & "Markdown Reader.command")
end run
