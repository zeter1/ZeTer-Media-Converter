# ZeTer Media Converter

Приложение для Windows: преобразование видео в MP3, объединение аудио курса
и разбивка на части до 10 часов. Также есть отдельный режим объединения видео.

## Установка

**Готовый Windows EXE:** [скачать в GitHub Releases](https://github.com/zeter1/ZeTer-Media-Converter/releases/latest).
Выберите `ZeTer-Media-Converter.exe` для Windows 10/11 x64.
EXE содержит FFmpeg, FFprobe, Python и Tkinter, без ручной настройки PATH.
Приложение не подписано цифровой подписью, поэтому Windows может
показать предупреждение SmartScreen.

**Запуск из исходников:** нужен Python с Tkinter и доступные в PATH
`ffmpeg` и `ffprobe`. Из корня репозитория:

```powershell
python "ZeTer Media Converter.py"
```

## Возможности

- Преобразование видео в MP3 для каждого исходного файла.
- Объединение курсов и разделение результата на части до 10 часов.
- Отдельная очередь для объединения видео.
- Постоянные уведомления о готовых результатах и переход в Проводник.
- Диагностика, журнал операций, восстановление предыдущих результатов.

Название программы — **ZeTer Media Converter**; константа `APP_NAME`
и версия `APP_VERSION=3.3.5` определены в `videovaudio/app.py`.
Точка запуска — `ZeTer Media Converter.py`. Технические имена
`videovaudio` и `VideoToAudioConverter` сохранены для совместимости.

При повторной обработке прежние MP3 сохраняются внутри
`Аудио для каждого видео/Предыдущие результаты/run_...`.
Файл `manifest.json` связывает исходные имена с резервными копиями.
Резервные копии автоматически не удаляются.

## Разработка, проверка и диагностика

Архитектура: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
Выполнение задач: [docs/FLOWS.md](docs/FLOWS.md).
Тесты: [docs/VERIFICATION.md](docs/VERIFICATION.md).
[Сборка и публикация EXE](docs/BUILD_WINDOWS.md).
История версий: [CHANGELOG.md](CHANGELOG.md).

```powershell
python tools/verify_project.py
python -B tools/test_audio_run_regressions.py
python -B tools/test_completion_notification.py
```

Для настоящих FFmpeg-регрессий нужен FFmpeg в PATH:
`python -B tools/test_audio_regressions.py`.

Готовые файлы отображаются в постоянном уведомлении справа внизу;
кнопка «Открыть расположение файла» выделяет результат в Проводнике.
Логи диагностики программа сохраняет в папке «Логи проблем» рядом с
исполняемым файлом. Не размещайте приватные логи и медиафайлы в Issues
без проверки их содержимого.

**Ограничения:** полное GUI-тестирование собранного EXE на
пользовательской Windows, GPU-кодеки и обработка многочасовых медиа
пока требуют ручной проверки. Бинарник без Authenticode-подписи.
