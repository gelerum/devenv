# Контейнер devenv для проекта, из которого запущен just: https://github.com/gelerum/devenv
# То же, что justfile, но compose-файлы - из main на GitHub, локальные правки не используются
# Ставится один раз (именно import, симлинк не подойдёт):
#   echo "import '$PWD/remote.just'" > ~/.justfile

set allow-duplicate-variables
src := "https://github.com/gelerum/devenv.git#main:"

import 'justfile'
