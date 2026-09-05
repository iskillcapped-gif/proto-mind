"""GitHub CLI connection and bounded read views; credentials stay with gh/Keychain."""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import stat
import subprocess
import sys
import tempfile

SCHEMA = "proto_mind.native_integrations.v1"
METHODS = {"github_status", "github_connect", "github_disconnect", "github_repositories", "github_repository"}
LOGIN = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}\Z")
REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}\Z")


def repository_name(value: object) -> str:
    if not isinstance(value, str) or not REPOSITORY.fullmatch(value) or value.split("/")[1] in {".", ".."}:
        raise ValueError("Некорректное имя репозитория GitHub.")
    return value


class GitHubConnection:
    def __init__(self, state: Path, *, user_home: Path | None = None, runner=subprocess.run):
        self.state = Path(state)
        self.path = self.state / "integrations.json"
        self.user_home = user_home or Path(pwd.getpwuid(os.getuid()).pw_dir)
        self.config = self.user_home / ".config" / "gh"
        self.runner = runner

    @property
    def executable(self) -> str | None:
        return next((str(p) for p in (Path("/opt/homebrew/bin/gh"), Path("/usr/local/bin/gh")) if os.access(p, os.X_OK)), None)

    def environment(self) -> dict[str, str]:
        # Only the gh child uses the real home, which its Keychain backend needs.
        # Never inherit API tokens, custom hosts, debug logging or arbitrary hooks.
        env = {key: value for key, value in os.environ.items() if key in {"PATH", "TMPDIR", "LANG", "LC_ALL", "USER"}}
        env.update(HOME=str(self.user_home), GH_CONFIG_DIR=str(self.config), GH_HOST="github.com",
                   GH_PROMPT_DISABLED="1", GH_NO_UPDATE_NOTIFIER="1", GH_TELEMETRY="false",
                   GIT_TERMINAL_PROMPT="0", PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin")
        return env

    def _json(self, args: list[str]):
        executable = self.executable
        if not executable:
            raise ValueError("Установите GitHub CLI, затем проверьте подключение.")
        try:
            result = self.runner([executable, *args], env=self.environment(), cwd=self.user_home,
                                 capture_output=True, timeout=25, text=True)
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError("GitHub не ответил. Проверьте подключение и повторите вручную.") from None
        if result.returncode:
            raise ValueError("GitHub не подтвердил запрос. Проверьте вход и доступ к репозиторию.")
        if len(result.stdout.encode("utf-8")) > 2 * 1024 * 1024:
            raise ValueError("Ответ GitHub слишком большой.")
        try:
            return json.loads(result.stdout)
        except (ValueError, RecursionError):
            raise ValueError("GitHub вернул непонятный ответ.") from None

    def _account(self) -> str | None:
        rows = self._json(["auth", "status", "--active", "--hostname", "github.com", "--json", "hosts", "--jq",
                           '.hosts["github.com"] // [] | map({login, active, state})'])
        if not isinstance(rows, list):
            raise ValueError("Не удалось проверить аккаунт GitHub.")
        active = [row.get("login") for row in rows if isinstance(row, dict) and row.get("active") is True and row.get("state") == "success"]
        return active[0] if len(active) == 1 and isinstance(active[0], str) and LOGIN.fullmatch(active[0]) else None

    def settings(self) -> dict:
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return {"schema": SCHEMA, "github": None}
        except OSError:
            raise ValueError("Не удалось прочитать подключение GitHub. Настройки не изменены.") from None
        try:
            with os.fdopen(fd, "rb") as handle:
                if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                    raise ValueError()
                raw = handle.read(8193)
            value = json.loads(raw) if len(raw) <= 8192 else None
            if not isinstance(value, dict) or set(value) != {"schema", "github"} or value["schema"] != SCHEMA:
                raise ValueError()
            account = value["github"]
            if account is not None and (not isinstance(account, dict) or set(account) != {"login"}
                                        or not isinstance(account["login"], str) or not LOGIN.fullmatch(account["login"])):
                raise ValueError()
            return value
        except (ValueError, OSError, RecursionError):
            raise ValueError("Настройки подключений повреждены. Автоматической перезаписи не было.") from None

    def status(self) -> dict:
        saved = self.settings()["github"]
        result = {"installed": self.executable is not None, "enabled": saved is not None,
                  "connected": False, "login": saved["login"] if saved else "", "available_login": "", "notice": ""}
        if not result["installed"]:
            result["notice"] = "Для подключения нужен GitHub CLI."
            return result
        try:
            login = self._account()
            result["available_login"] = login or ""
            result["connected"] = bool(saved and login == saved["login"])
            if saved and login != saved["login"]:
                result["notice"] = "Вход GitHub изменился или недоступен. Проверьте аккаунт и подключите его снова."
            elif not login:
                result["notice"] = "Войдите в GitHub CLI на этом Mac, затем нажмите «Проверить»."
        except ValueError as exc:
            result["notice"] = str(exc)
        return result

    def _write(self, value: dict) -> None:
        raw = (json.dumps(value, sort_keys=True) + "\n").encode()
        fd, name = tempfile.mkstemp(prefix=".integrations-", dir=self.state)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw); handle.flush(); os.fsync(handle.fileno())
            os.replace(name, self.path)
            directory = os.open(self.state, os.O_RDONLY)
            try: os.fsync(directory)
            finally: os.close(directory)
            if self.settings() != value:
                raise ValueError("Не удалось подтвердить сохранение подключения. Проверьте состояние перед повтором.")
        finally:
            if os.path.exists(name): os.unlink(name)

    def connect(self, login: object) -> dict:
        if not isinstance(login, str) or not LOGIN.fullmatch(login):
            raise ValueError("Сначала проверьте аккаунт GitHub.")
        return self._change(login)

    def disconnect(self) -> dict:
        return self._change(None)

    def _change(self, login: str | None) -> dict:
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.state / ".integrations.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            self.settings()  # Never replace malformed or symlinked settings.
            if login is not None:
                if self._account() != login:
                    raise ValueError("Аккаунт GitHub изменился. Проверьте подключение ещё раз.")
                self._install_command()
            self._write({"schema": SCHEMA, "github": {"login": login} if login else None})
        finally:
            os.close(fd)
        return self.status() if login else {"installed": self.executable is not None, "enabled": False, "connected": False,
                                            "login": "", "available_login": "", "notice": "Подключение выключено. Вход GitHub CLI на Mac сохранён."}

    def _install_command(self) -> None:
        directory = self.state / "integration-bin"
        if directory.is_symlink():
            raise ValueError("Папка подключения должна быть обычной папкой.")
        directory.mkdir(exist_ok=True, mode=0o700)
        target = directory / "proto-github"
        script = Path(__file__).resolve().parent.parent / "scripts" / "native_github_cli.py"
        if not script.is_file():
            raise ValueError("Компонент подключения GitHub отсутствует. Обновите приложение.")
        command = "#!/bin/sh\nexec " + " ".join(shlex.quote(str(p)) for p in [sys.executable, script, self.state]) + ' "$@"\n'
        fd, name = tempfile.mkstemp(prefix=".github-", dir=directory)
        try:
            with os.fdopen(fd, "w") as handle:
                handle.write(command); handle.flush(); os.fsync(handle.fileno())
            os.chmod(name, 0o700)
            os.replace(name, target)
            folder = os.open(directory, os.O_RDONLY)
            try: os.fsync(folder)
            finally: os.close(folder)
        finally:
            if os.path.exists(name): os.unlink(name)

    def require_connection(self) -> str:
        saved = self.settings()["github"]
        if not saved:
            raise ValueError("Подключите GitHub в настройках Proto-Mind.")
        if self._account() != saved["login"]:
            raise ValueError("Подключённый аккаунт GitHub недоступен или изменился. Проверьте настройки подключений.")
        return saved["login"]

    def runtime_environment(self) -> dict[str, str]:
        if self.settings()["github"] is None:
            return {}
        helper = self.state / "integration-bin" / "proto-github"
        if not helper.is_file() or helper.is_symlink() or not os.access(helper, os.X_OK):
            raise ValueError("Команда GitHub недоступна. Переподключите GitHub в настройках.")
        return {"PROTO_MIND_GITHUB_BIN": str(helper.parent), "GIT_CONFIG_COUNT": "2",
                "GIT_CONFIG_KEY_0": "credential.https://github.com.helper", "GIT_CONFIG_VALUE_0": "",
                "GIT_CONFIG_KEY_1": "credential.https://github.com.helper",
                "GIT_CONFIG_VALUE_1": "!" + shlex.quote(str(helper)) + " auth git-credential", "GIT_TERMINAL_PROMPT": "0"}

    def repositories(self, page: object = 1) -> dict:
        if type(page) is not int or not 1 <= page <= 1000:
            raise ValueError("Некорректная страница GitHub.")
        login = self.require_connection()
        rows = self._json(["api", "user/repos", "--method", "GET", "-f", "per_page=30", "-f", f"page={page}", "-f", "sort=updated", "-f", "type=all"])
        if not isinstance(rows, list) or len(rows) > 30:
            raise ValueError("Некорректный список репозиториев GitHub.")
        items = []
        for row in rows:
            name = repository_name(row.get("full_name") if isinstance(row, dict) else None)
            items.append({"name": name, "url": "https://github.com/" + name, "private": row.get("private") is True,
                          "description": str(row.get("description") or "")[:500]})
        return {"login": login, "items": items, "next_page": page + 1 if len(rows) == 30 and page < 1000 else None}

    def repository(self, name: object) -> dict:
        name = repository_name(name)
        self.require_connection()
        result = {"name": name, "url": "https://github.com/" + name}
        for kind in ("pr", "issue"):
            rows = self._json([kind, "list", "--repo", name, "--limit", "20", "--state", "open", "--json", "number,title"])
            if not isinstance(rows, list) or len(rows) > 20:
                raise ValueError("Некорректный список задач GitHub.")
            projected = []
            for row in rows:
                number = row.get("number") if isinstance(row, dict) else None
                if type(number) is not int or not 0 < number < 2**31 or not isinstance(row.get("title"), str):
                    raise ValueError("Некорректная задача GitHub.")
                projected.append({"number": number, "title": row["title"][:300],
                                  "url": f'https://github.com/{name}/{"pull" if kind == "pr" else "issues"}/{number}'})
            result[kind] = projected
        return result

    def dispatch(self, method: str, params: dict) -> dict:
        expected = {"github_connect": {"login"}, "github_repositories": {"page"}, "github_repository": {"name"}}.get(method, set())
        if set(params) - expected:
            raise ValueError("Неожиданные параметры подключения GitHub.")
        if method == "github_connect": return self.connect(params.get("login"))
        if method == "github_disconnect": return self.disconnect()
        if method == "github_repositories": return self.repositories(params.get("page", 1))
        if method == "github_repository": return self.repository(params.get("name"))
        if method == "github_status": return self.status()
        raise ValueError("Неизвестная операция GitHub.")
