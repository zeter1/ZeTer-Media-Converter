# Сборка и публикация EXE для Windows

## Готовый бинарник

Версия приложения: **3.3.5** (Windows 10/11, x64).
[Скачать последний опубликованный релиз](https://github.com/zeter1/ZeTer-Media-Converter/releases/latest).

Файл **ZeTer-Media-Converter.exe** содержит Python, Tkinter, FFmpeg и FFprobe.
Пользователю не нужно устанавливать Python или добавлять FFmpeg в PATH.

При первом запуске файл распаковывает встроенные зависимости во временный
каталог PyInstaller; это обычное поведение режима `--onefile`.
Результаты обработки сохраняются по обычным правилам приложения.
Windows SmartScreen может предупреждать о неподписанном исполняемом файле.

## Воспроизводимая сборка

Используется [build-windows.yml](../.github/workflows/build-windows.yml):
Windows GitHub runner, Python 3.12, PyInstaller 6.22.3 и отдельные
FFmpeg/FFprobe 9.0.2 essentials (GPLv3).
Архив FFmpeg скачивается по фиксированной версии и проверяется по SHA256
до распаковки и запуска. FFmpeg исполняемые файлы помещаются внутрь
`--onefile` EXE через `--add-binary`, а
`packaging/runtime_ffmpeg_path.py` добавляет только внутренний
путь PyInstaller в PATH запускаемого процесса.

Пайплайн запускается при изменении самого workflow в `main`
(однократное создание сборки) или вручную через `workflow_dispatch`.
Обычные commits исходников и README **не публикуют релизы**.
Повторная публикация существующего тега запрещена; следующая версия
требует осознанного изменения номера релиза.

## Гейты и ограничения

Перед выпуском: architecture/import test, run lifecycle, notification tests,
реальные аудиорегрессии FFmpeg, frozen `--verify-bundle`, проверка SHA256 EXE
и полноты файла лицензии. Проверка `--verify-bundle` запускает
уже собранный файл и проверяет встроенные FFmpeg, FFprobe и импорт приложения,
но не создаёт настоящее Tkinter-окно.

Полная GUI-проверка, преобразование длинных курсов и проверка
антивирусами на пользовательской машине — **NOT VERIFIED** до реального
ручного тестирования. Релизные файлы не подписаны Authenticode.

FFmpeg GPLv3 и ссылка на соответствующие исходники указаны в
`packaging/THIRD_PARTY_NOTICES.txt`; тот же файл и лицензия GPLv3
прикладываются к GitHub Release.
