## Security policy

Chameleon edits files inside your Dota 2 installation (a mod folder, `gameinfo_branchspecific.gi`, `dota.signatures`)
and downloads two small kinds of data on request (icons from Steam's CDN, and the menu-layout files from
`h6rd/BackgroundChanger`). It never reads or sends account data.

Found a vulnerability (for example a path traversal in preset or font handling)? Please open a private
security advisory on GitHub instead of a public issue. You will get an answer within a week.


## Политика безопасности

Chameleon вносит изменения в файлы установленной игры Dota 2 (папка с модами, `gameinfo_branchspecific.gi`, `dota.signatures`)
и по запросу загружает два небольших набора данных: иконки из CDN Steam и файлы компоновки меню из
репозитория `h6rd/BackgroundChanger`. Программа не считывает и не передает данные учетной записи.

Обнаружили уязвимость (например, уязвимость типа path traversal при обработке пресетов или шрифтов)?
Пожалуйста, создайте приватное сообщение о проблеме безопасности (security advisory) на GitHub,
а не публичный тикет (issue). Вы получите ответ в течение недели.
