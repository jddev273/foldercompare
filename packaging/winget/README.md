# WinGet

Generate and validate the WinGet manifest only after the current safe release succeeds, using its exact versioned installer URL and SHA-256. Validate with `wingetcreate` against the then-current WinGet schema before submission to `microsoft/winget-pkgs`.
