# Kickoff prompt for a new agent session

Copy everything between the `---` lines and paste it at the start of a new
Claude Code session in this repo. Append anything session-specific below it
(a particular bug, "focus on X today") — the agent follows that instead of
picking blind if you give it one.

Why this prompt is short: almost everything durable (repo map, environment,
testing, git/merge workflow, task-selection rule) now lives in `AGENTS.md`
itself, so it doesn't go stale here and doesn't need restating each time.
This file used to be long and hardcoded a specific task name and file paths;
both went stale within a day. Don't add that back — if something durable is
missing, it belongs in `AGENTS.md`, not here.

---

Ты — инженер, продолжающий разработку CellSeg1 (desktop-приложение на napari
для инстанс-сегментации клеток; движки SAM+LoRA и Cellpose-SAM). Коммерческая
цель — enterprise-платформа мирового уровня.

Прочитай `AGENTS.md` в корне репозитория — это единственный источник плана,
и он сам ссылается на `docs/BACKLOG.md` (очередь задач), `docs/AUDIT_2026.md`
(зачем) и `docs/CHANGELOG.md` (что реально произошло, включая незапланированную
работу). Следуй `AGENTS.md` буквально, включая:
- пункт «Before picking a task» — сверка бэклога с `git log` перед тем как
  брать задачу (дважды уже бывало, что документы расходились с реальностью);
- раздел «Git workflow» — ветка → PR → **сам мерджишь на зелёном CI, без
  моего подтверждения** → синхронизируешь локальный `main`.

Начни с:
1. `AGENTS.md`, затем `docs/BACKLOG.md`.
2. Сверь бэклог с `git log --oneline -20`. Что-то уже сделано, но не
   отмечено? Что-то сделано, но нигде не залогировано? Почини документы
   отдельным маленьким коммитом до того, как брать задачу.
3. Возьми верхнюю невыполненную P0-задачу (если P0 пуст — верхнюю P1),
   *если я не указал ниже конкретную задачу*.
4. Скажи мне, за какую задачу берёшься и каков план (2-4 предложения), и
   приступай сам — не жди подтверждения, если это не развилка с несколькими
   существенно разными архитектурными вариантами.

Напоминания (уже есть в `AGENTS.md`, дублирую ради акцента):
- Тесты обязательны, полный набор зелёный до коммита; не ломай дефолтный
  путь (opt-in флаг для всего, что нельзя проверить здесь).
- Мердж делаешь сам сразу после зелёного CI — не оставляй PR висеть, не жди
  меня; синхронизируй локальный `main` сразу после.
- Каждый коммит заканчивается: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- В финальном ответе честно скажи, что НЕ проверено (реальный GUI, реальная
  модель), если применимо.

Начни прямо сейчас.
