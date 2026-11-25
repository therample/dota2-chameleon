# Security policy

Chameleon edits files inside your Dota 2 installation (a mod folder, `gameinfo_branchspecific.gi`, `dota.signatures`)
and downloads two small kinds of data on request (icons from Steam's CDN, and the menu-layout files from
`h6rd/BackgroundChanger`). It never reads or sends account data.

Found a vulnerability (for example a path traversal in preset or font handling)? Please open a private
security advisory on GitHub instead of a public issue. You will get an answer within a week.
