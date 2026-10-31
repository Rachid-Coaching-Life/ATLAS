"""Local task queue for prompts submitted by interactive clients."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
import threading
from math import isfinite
from pathlib import Path
import os
import re
import stat
import time
import unicodedata
import uuid
from typing import Callable, Optional

from .debug import debug_log
from .utils.redact import redact

DEFAULT_TASK_HISTORY = 200
TASK_EVENT_PREFIX = "__TASK__:"


def run_reply_engine(*args, **kwargs):
    """Load the reply engine only when a task actually starts."""
    from .reply.engine import run_reply_engine as _run_reply_engine
    return _run_reply_engine(*args, **kwargs)


_DIRECT_SYSTEM_STATUS_COMMANDS = frozenset({
    "diagnostic systeme",
    "etat du systeme",
    "etat systeme",
    "diagnostic de mon ordinateur",
    "verifie l etat de mon ordinateur",
    "verifie l etat de mon pc",
})


def _normalized_task_intent(prompt: str) -> str:
    """Accent-insensitive exact-match key; never extract an action from prose."""
    if not isinstance(prompt, str):
        return ""
    unaccented = "".join(
        letter for letter in unicodedata.normalize("NFKD", prompt)
        if not unicodedata.combining(letter)
    ).casefold()
    return re.sub(r"[^a-z0-9]+", " ", unaccented).strip()


def _is_direct_system_status_task(prompt: str) -> bool:
    """Only exact, harmless system-status requests bypass LLM planning."""
    return _normalized_task_intent(prompt) in _DIRECT_SYSTEM_STATUS_COMMANDS


_DIRECT_FILE_LIST_COMMANDS = {
    "liste mes documents": "Documents",
    "liste les fichiers de mes documents": "Documents",
    "liste les fichiers de mon dossier documents": "Documents",
    "liste mes telechargements": "Downloads",
    "liste les fichiers de mes telechargements": "Downloads",
    "liste les fichiers de mon bureau": "Desktop",
}


def _direct_file_list_folder(prompt: str) -> Optional[str]:
    """Recognise only simple file-listing requests, never mutating actions."""
    return _DIRECT_FILE_LIST_COMMANDS.get(_normalized_task_intent(prompt))


_DIRECT_PDF_LIST_COMMANDS = {
    "liste les pdf de mes documents": "Documents",
    "liste les fichiers pdf de mes documents": "Documents",
    "liste les pdf de mes telechargements": "Downloads",
    "liste les fichiers pdf de mes telechargements": "Downloads",
    "liste les pdf de mon bureau": "Desktop",
    "liste les fichiers pdf de mon bureau": "Desktop",
}


def _direct_pdf_list_folder(prompt: str) -> Optional[str]:
    """Exact, nonrecursive and read-only local PDF listing requests only."""
    return _DIRECT_PDF_LIST_COMMANDS.get(_normalized_task_intent(prompt))


_DIRECT_RECURSIVE_PDF_COMMANDS = {
    "recherche les pdf dans mes documents et sous dossiers": "Documents",
    "cherche les pdf dans mes documents et sous dossiers": "Documents",
    "recherche les pdf dans mes telechargements et sous dossiers": "Downloads",
    "cherche les pdf dans mes telechargements et sous dossiers": "Downloads",
    "recherche les pdf dans mon bureau et sous dossiers": "Desktop",
    "cherche les pdf dans mon bureau et sous dossiers": "Desktop",
}


def _direct_recursive_pdf_folder(prompt: str) -> Optional[str]:
    """Only opt-in PDF searches across subfolders, with hard traversal bounds."""
    return _DIRECT_RECURSIVE_PDF_COMMANDS.get(_normalized_task_intent(prompt))


def _local_inventory_directory(folder: str) -> Path:
    """Use an existing home folder or known local OneDrive relocation only.

    Symlinks outside the profile are intentionally rejected by localFiles.
    Never create a missing folder or search the whole disk.
    """
    if folder not in {"Documents", "Downloads", "Desktop"}:
        raise ValueError("Dossier de consultation inconnu")
    home = Path.home().resolve()
    candidates = [home / folder, home / "OneDrive" / folder]
    for key in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        cloud_root = os.environ.get(key)
        if cloud_root:
            candidates.append(Path(cloud_root) / folder)
    for path in candidates:
        if path.is_dir():
            resolved = path.resolve()
            if resolved.is_relative_to(home):
                return resolved
    raise FileNotFoundError(
        f"Le dossier {folder} n'a pas été trouvé dans le profil local."
    )


def _has_pdf_open_intent(prompt: str) -> bool:
    """Prevent invalid PDF-open paths from falling back to an LLM/tool router."""
    return isinstance(prompt, str) and bool(
        re.match(r"^ouvre\s+le\s+pdf\b", prompt.strip(), re.IGNORECASE)
    )


def _direct_pdf_open_request(prompt: str) -> Optional[tuple[str, tuple[str, ...]]]:
    """Parse an explicit relative PDF path from one user instruction.

    No absolute paths, drive letters, UNC paths, parent traversal,
    wildcards or extra commands. No guessing filenames from prior lists.
    """
    if not isinstance(prompt, str):
        return None
    match = re.fullmatch(r"ouvre\s+le\s+pdf\s+(.+)", prompt.strip(), re.IGNORECASE)
    if match is None:
        return None
    raw_path = match.group(1)
    if re.search(r'[\x00-\x1f<>:"|?*]', raw_path):
        return None
    parts = re.split(r"[\\/]", raw_path)
    if len(parts) < 2 or any(
        not part or part in {".", ".."} or part.endswith((" ", "."))
        for part in parts
    ):
        return None
    folders = {
        "documents": "Documents",
        "downloads": "Downloads",
        "telechargements": "Downloads",
        "desktop": "Desktop",
        "bureau": "Desktop",
    }
    folder_key = _normalized_task_intent(parts[0])
    folder = folders.get(folder_key)
    if folder is None or not parts[-1].casefold().endswith(".pdf"):
        return None
    return folder, tuple(parts[1:])


def _open_explicit_local_pdf(folder: str, relative_parts: tuple[str, ...]) -> str:
    """Ask Windows to open one validated PDF; never alter it or execute shell."""
    root = _local_inventory_directory(folder)
    current = root
    for part in relative_parts:
        current = current / part
        details = current.lstat()  # No link-following before validation.
        if (stat.S_ISLNK(details.st_mode)
                or getattr(details, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise PermissionError("Ouverture refusée : lien ou jonction Windows.")
    resolved = current.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise PermissionError("Ouverture refusée : fichier hors du dossier autorisé.")
    if resolved.suffix.casefold() != ".pdf":
        raise ValueError("Le fichier demandé n'est pas un PDF.")
    with resolved.open("rb") as handle:
        if handle.read(5) != b"%PDF-":
            raise ValueError("Le fichier n'a pas d'en-tête PDF valide.")
    launcher = getattr(os, "startfile", None)
    if launcher is None:
        raise RuntimeError("L'ouverture directe est disponible uniquement sous Windows.")
    launcher(str(resolved))  # OS file association, never a shell command.
    return (
        "Demande d'ouverture transmise à Windows : "
        + str(Path(folder).joinpath(*relative_parts))
        + ". Vérifiez que votre lecteur PDF affiche le document."
    )


_SPOKEN_OPEN_PREFIX = re.compile(
    r"^ouvre\s+(?:(?:mon|ma|mes)\s+|(?:le|la)\s+(?:document|fichier)\s+)",
    re.IGNORECASE,
)


def _has_spoken_pdf_open_intent(prompt: str) -> bool:
    """Conservative natural file request, never a general app launcher."""
    return isinstance(prompt, str) and bool(_SPOKEN_OPEN_PREFIX.match(prompt.strip()))


def _direct_spoken_pdf_request(prompt: str) -> Optional[tuple[str, Optional[str]]]:
    """A spoken filename hint, with an optional named user folder.

    Compound actions, paths and explicit scripts are never accepted.
    """
    if not _has_spoken_pdf_open_intent(prompt):
        return None
    remainder = _SPOKEN_OPEN_PREFIX.sub("", prompt.strip(), count=1).strip()
    remainder = remainder.rstrip(" .!?").strip()
    if re.search(r'[\\/:*?"<>|\x00-\x1f]', remainder):
        return None
    if re.search(
        r"\b(?:et|puis|ensuite|supprime|efface|deplace|execute|lance)\b",
        _normalized_task_intent(remainder),
    ):
        return None
    folder = None
    hints = (
        (r"\s+sur\s+le\s+bureau$", "Desktop"),
        (r"\s+dans\s+mes\s+documents$", "Documents"),
        (r"\s+dans\s+mes\s+telechargements$", "Downloads"),
    )
    for ending, target in hints:
        # All folder labels are matched on accent-stripped text so ASR
        # and ordinary French spelling use the same deterministic route.
        normalized = _normalized_task_intent(remainder)
        if re.search(ending, normalized):
            prefix = re.sub(ending, "", normalized)
            remainder, folder = prefix, target
            break
    remainder = remainder.rstrip(" .!?").strip()
    if remainder.casefold().endswith(".pdf"):
        remainder = remainder[:-4].rstrip()
    if not (3 <= len(remainder) <= 100) or not _normalized_task_intent(remainder):
        return None
    return remainder, folder


def _find_spoken_named_pdf(title: str, folder_hint: Optional[str] = None) -> tuple[str, tuple[str, ...]]:
    """Locate exactly one PDF by spoken name without opening it.

    A partial search or multiple filename matches never opens anything.
    """
    from .tools.builtin.local_files import _bounded_pdf_search

    folders = (folder_hint,) if folder_hint else ("Desktop", "Documents", "Downloads")
    home = Path.home().resolve()
    deadline = time.monotonic() + 3.0
    needle = _normalized_task_intent(title)
    candidates: list[tuple[str, tuple[str, ...]]] = []
    incomplete = False
    for folder in folders:
        try:
            root = _local_inventory_directory(folder)
        except FileNotFoundError:
            if folder_hint:
                raise
            continue
        output = _bounded_pdf_search(root, home, deadline=deadline)
        if "Recherche partielle :" in output:
            incomplete = True
        for line in output.splitlines():
            if not line.startswith("  PDF: "):
                continue
            path = Path(line[len("  PDF: "):])
            words = _normalized_task_intent(path.stem)
            if (" " + needle + " ") in (" " + words + " "):
                candidates.append((folder, tuple(path.parts)))
    if incomplete:
        raise RuntimeError(
            "Recherche PDF incomplète. Précisez le dossier et le nom exact "
            "du fichier avant toute ouverture."
        )
    if not candidates:
        raise FileNotFoundError(
            f"Aucun PDF correspondant à « {title} » dans les dossiers autorisés. "
            "Précisez son nom ou son dossier."
        )
    if len(candidates) != 1:
        descriptions = [
            str(Path(folder).joinpath(*parts))
            for folder, parts in candidates[:3]
        ]
        raise ValueError(
            f"Plusieurs PDF correspondent à « {title} » : "
            + " ; ".join(descriptions)
            + ". Précisez le dossier et le nom du fichier."
        )
    folder, parts = candidates[0]
    return folder, parts


def _open_spoken_named_pdf(title: str, folder_hint: Optional[str] = None) -> str:
    folder, parts = _find_spoken_named_pdf(title, folder_hint)
    return _open_explicit_local_pdf(folder, parts)


_READ_PDF_PREFIX = re.compile(r"^lis(?:-moi| moi)?\\s+", re.IGNORECASE)


def _direct_spoken_pdf_read_request(prompt: str) -> Optional[tuple[str, Optional[str]]]:
    """Reuse the existing strict filename parser; never accept compound actions."""
    if not isinstance(prompt, str) or not _READ_PDF_PREFIX.match(prompt.strip()):
        return None
    opening = _READ_PDF_PREFIX.sub("Ouvre ", prompt.strip(), count=1)
    return _direct_spoken_pdf_request(opening)


def _has_spoken_pdf_read_intent(prompt: str) -> bool:
    return isinstance(prompt, str) and bool(_READ_PDF_PREFIX.match(prompt.strip()))


def _read_spoken_named_pdf(title: str, folder_hint: Optional[str] = None) -> str:
    """Read only a bounded preview, without opening a viewer or changing the PDF."""
    from .tools.builtin.pdf_extract import extract_pdf_text

    folder, parts = _find_spoken_named_pdf(title, folder_hint)
    root = _local_inventory_directory(folder)
    relative = Path(*parts)
    extracted = extract_pdf_text(relative, root, max_pages=3)
    content = " ".join(text.strip() for _, text in extracted.pages if text.strip())
    if not content:
        raise ValueError("Ce PDF ne contient pas de texte extractible. Aucun OCR n'a été effectué.")
    preview = content[:1200]
    partial = extracted.truncated or len(content) > 1200
    return (
        f"Lecture du document {relative.name}, pages examinées : "
        f"{len(extracted.pages)} sur {extracted.total_pages}. "
        + preview
        + (" Fin de l'extrait, lecture partielle." if partial else " Fin du document.")
    )


def _direct_voice_task_prompt(
    query: str, wake_word: str = "ATLAS", wake_aliases=(),
    *, pending_pdf_title: Optional[str] = None,
) -> Optional[str]:
    """Strip a *leading* wake address and select existing deterministic tasks.

    Only called after the listener's ordinary wake/engagement acceptance.
    Other requests stay in the normal voice reply engine.
    """
    if not isinstance(query, str):
        return None
    clean = query.strip()
    names = sorted(
        {n.strip() for n in ("ATLAS", wake_word, *(wake_aliases or ()))
         if isinstance(n, str) and n.strip()},
        key=len, reverse=True,
    )
    if names:
        escaped = "|".join(re.escape(name) for name in names)
        clean = re.sub(
            rf"^(?:{escaped})(?:\s*[,.:!?]\s*|\s+)",
            "", clean, count=1, flags=re.IGNORECASE,
        ).strip()
    if pending_pdf_title:
        folder_followups = {
            "sur le bureau": "sur le bureau",
            "bureau": "sur le bureau",
            "dans mes documents": "dans mes documents",
            "mes documents": "dans mes documents",
            "dans mes telechargements": "dans mes téléchargements",
            "mes telechargements": "dans mes téléchargements",
        }
        qualifier = folder_followups.get(_normalized_task_intent(clean))
        if qualifier:
            return f"Ouvre mon {pending_pdf_title} {qualifier}"
    if (
        _is_direct_system_status_task(clean)
        or _direct_file_list_folder(clean) is not None
        or _direct_pdf_list_folder(clean) is not None
        or _direct_recursive_pdf_folder(clean) is not None
        or _has_pdf_open_intent(clean)
        or _has_spoken_pdf_open_intent(clean)
        or _has_spoken_pdf_read_intent(clean)
    ):
        return clean
    return None


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    id: str
    prompt: str
    status: TaskStatus = TaskStatus.QUEUED
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    def as_dict(self) -> dict:
        return {
            "type": "task",
            "id": self.id,
            "prompt": self.prompt,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class TaskManager:
    """Execute prompts through the normal reply engine in a bounded queue."""

    def __init__(
        self,
        db,
        cfg,
        dialogue_memory,
        event_callback: Optional[Callable[[dict], None]] = None,
        max_workers: int = 1,
        max_queued_tasks: int = 100,
        max_history: int = DEFAULT_TASK_HISTORY,
    ) -> None:
        for limit in (max_queued_tasks, max_history):
            if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
                raise ValueError("Task capacity and history limits must be a positive integer")
        self.db = db
        self.cfg = cfg
        self.dialogue_memory = dialogue_memory
        self.event_callback = event_callback
        self.max_queued_tasks = max_queued_tasks
        self.max_history = max_history
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="jarvis-task")
        self._tasks: dict[str, Task] = {}
        self._futures: dict[str, Future] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._lock = threading.RLock()
        self._closed = False
        self._restore()

    def submit(self, prompt: str) -> str:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("Task prompt cannot be empty")
        task = Task(id=uuid.uuid4().hex[:12], prompt=prompt)
        with self._lock:
            if self._closed:
                raise RuntimeError("Task service is stopping")
            active = sum(not future.done() for future in self._futures.values())
            if active >= self.max_queued_tasks:
                raise RuntimeError("Task queue is full")
            self._tasks[task.id] = task
            self._cancel_events[task.id] = threading.Event()
            self._persist(task)
            self._prune_history()
            self._emit(task)
            self._futures[task.id] = self._executor.submit(self._run, task.id)
        print(f'📋 Queued task: "{redact(task.prompt)}"', flush=True)
        debug_log(f"task submitted: {task.id}", "tasks")
        return task.id

    def get(self, task_id: str) -> Optional[Task]:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self) -> list[Task]:
        with self._lock:
            return sorted(self._tasks.values(), key=lambda task: task.created_at, reverse=True)

    def wait_for_task(self, task_id: str, timeout: float = 12.0) -> Optional[Task]:
        """Wait only for this task; the HUD keeps independent progress events."""
        with self._lock:
            future = self._futures.get(task_id)
        if future is None:
            return None
        future.result(timeout=timeout)
        return self.get(task_id)

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.status in {
                TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED,
            }:
                return False
            self._cancel_events.setdefault(task.id, threading.Event()).set()
            task.status = TaskStatus.CANCELLED
            task.completed_at = time.time()
            self._persist(task)
            self._emit(task)
            debug_log(f"task cancelled: {task.id}", "tasks")
            return True

    def wait_for_idle(self, timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if all(future.done() for future in self._futures.values()):
                    return
            time.sleep(0.01)
        raise TimeoutError("Timed out waiting for task queue")

    def shutdown(self, wait: bool = True) -> None:
        with self._lock:
            self._closed = True
            for task_id, task in self._tasks.items():
                if task.status in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
                    self._cancel_events.setdefault(task_id, threading.Event()).set()
                    task.status = TaskStatus.CANCELLED
                    task.completed_at = time.time()
                    self._persist(task)
                    self._emit(task)
                    debug_log(f"task stop requested during shutdown: {task_id}", "tasks")
        self._executor.shutdown(wait=wait, cancel_futures=True)

    def _run(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks[task_id]
            if task.status is TaskStatus.CANCELLED:
                return
            task.status = TaskStatus.RUNNING
            task.started_at = time.time()
            cancel_event = self._cancel_events.setdefault(task.id, threading.Event())
            self._persist(task)
            self._emit(task)
        try:
            if _is_direct_system_status_task(task.prompt):
                # A read-only, deterministic action: no tool router,
                # inference, network or extra daemon is required.
                from .tools.registry import run_tool_with_retries
                outcome = run_tool_with_retries(
                    self.db, self.cfg, "systemStatus", {}, "",
                    task.prompt, redact(task.prompt), max_retries=0,
                )
                if not outcome.success:
                    raise RuntimeError(
                        outcome.error_message or outcome.reply_text
                        or "Diagnostic système indisponible."
                    )
                result = outcome.reply_text
            elif (
                (folder := _direct_file_list_folder(task.prompt)) is not None
                or (folder := _direct_pdf_list_folder(task.prompt)) is not None
            ):
                # Keep the existing localFiles sandbox and nonrecursive limit.
                # Never search another volume or infer a destructive action.
                from .tools.registry import run_tool_with_retries
                pdf_only = _direct_pdf_list_folder(task.prompt) is not None
                directory = _local_inventory_directory(folder)
                outcome = run_tool_with_retries(
                    self.db, self.cfg, "localFiles",
                    {"operation": "list", "path": str(directory),
                     "recursive": False, "glob": "*.pdf" if pdf_only else "*"},
                    "", task.prompt, redact(task.prompt), max_retries=0,
                )
                if not outcome.success:
                    raise RuntimeError(
                        outcome.error_message or outcome.reply_text
                        or f"Impossible de lister {folder}."
                    )
                scope = "PDF du dossier " if pdf_only else ""
                result = (
                    f"Inventaire en lecture seule : {scope}{folder} "
                    "(premier niveau uniquement, 50 entrées affichées au maximum).\n"
                    + (outcome.reply_text or "Aucun détail disponible.")
                )
            elif (folder := _direct_recursive_pdf_folder(task.prompt)) is not None:
                # The existing localFiles tool now supports bounded read-only
                # PDF traversal. This path never opens or changes documents.
                from .tools.registry import run_tool_with_retries
                directory = _local_inventory_directory(folder)
                outcome = run_tool_with_retries(
                    self.db, self.cfg, "localFiles",
                    {"operation": "search", "path": str(directory),
                     "file_type": "pdf"},
                    "", task.prompt, redact(task.prompt), max_retries=0,
                )
                if not outcome.success:
                    raise RuntimeError(
                        outcome.error_message or outcome.reply_text
                        or "Recherche PDF indisponible."
                    )
                result = outcome.reply_text
            elif _has_pdf_open_intent(task.prompt):
                # Invalid requests fail closed; they must never fall through
                # to unconstrained LLM/tool routing.
                requested_pdf = _direct_pdf_open_request(task.prompt)
                if requested_pdf is None:
                    raise ValueError(
                        "Ouverture refusée : indiquez un chemin PDF relatif "
                        "dans Documents, Téléchargements ou Bureau."
                    )
                folder, relative_parts = requested_pdf
                result = _open_explicit_local_pdf(folder, relative_parts)
            elif _has_spoken_pdf_read_intent(task.prompt):
                requested_pdf = _direct_spoken_pdf_read_request(task.prompt)
                if requested_pdf is None:
                    raise ValueError("Demande de lecture ambiguë : précisez uniquement le nom du PDF.")
                title, folder_hint = requested_pdf
                result = _read_spoken_named_pdf(title, folder_hint)
            elif _has_spoken_pdf_open_intent(task.prompt):
                requested_pdf = _direct_spoken_pdf_request(task.prompt)
                if requested_pdf is None:
                    raise ValueError("Demande d'ouverture ambiguë : précisez uniquement le nom du PDF.")
                title, folder_hint = requested_pdf
                result = _open_spoken_named_pdf(title, folder_hint)
            else:
                from .daemon import query_lock
                with query_lock():
                    result = run_reply_engine(
                        self.db, self.cfg, None, task.prompt, self.dialogue_memory,
                        quiet=True, cancel_event=cancel_event,
                    )
            with self._lock:
                if task.status is not TaskStatus.CANCELLED:
                    task.status = TaskStatus.COMPLETED
                    task.result = redact(result or "")
                    task.completed_at = time.time()
                    self._persist(task)
                    self._emit(task)
                    if task.result:
                        print(f"📋 Task result: {task.result}", flush=True)
                else:
                    self._persist(task)
        except Exception as exc:
            with self._lock:
                if task.status is not TaskStatus.CANCELLED:
                    task.status = TaskStatus.FAILED
                    task.error = redact(str(exc))
                    task.completed_at = time.time()
                    self._persist(task)
                    self._emit(task)
            debug_log(f"task failed: {task_id} ({type(exc).__name__})", "tasks")

    def _emit(self, task: Task) -> None:
        if self.event_callback is None:
            return
        try:
            event = task.as_dict()
            event["prompt"] = redact(task.prompt)
            if event["result"]:
                event["result"] = redact(str(event["result"]))
            if event["error"]:
                event["error"] = redact(str(event["error"]))
            self.event_callback(event)
        except Exception as exc:
            debug_log(f"task event callback failed ({type(exc).__name__})", "tasks")

    def _prune_history(self) -> None:
        terminal = sorted(
            (task for task in self._tasks.values()
             if task.status in {
                 TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED
             } and (task.id not in self._futures or self._futures[task.id].done())),
            key=lambda task: task.created_at,
        )
        for task in terminal[:-self.max_history]:
            self._tasks.pop(task.id, None)
            self._futures.pop(task.id, None)
            self._cancel_events.pop(task.id, None)
        if hasattr(self.db, "prune_task_records"):
            try:
                self.db.prune_task_records(self.max_history)
            except Exception as exc:
                debug_log(f"task history pruning failed ({type(exc).__name__})", "tasks")

    def _persist(self, task: Task) -> None:
        if not hasattr(self.db, "upsert_task_record"):
            return
        record = task.as_dict()
        record["prompt"] = redact(task.prompt)
        if record["result"]:
            record["result"] = redact(str(record["result"]))
        if record["error"]:
            record["error"] = redact(str(record["error"]))
        try:
            self.db.upsert_task_record(record)
        except Exception as exc:
            debug_log(f"task persistence failed ({type(exc).__name__})", "tasks")

    def _restore(self) -> None:
        if not hasattr(self.db, "get_task_records"):
            return
        try:
            rows = self.db.get_task_records()
        except Exception as exc:
            debug_log(f"task restore failed ({type(exc).__name__})", "tasks")
            return
        for row in rows:
            try:
                task = Task(
                    id=row["id"], prompt=row["prompt"],
                    status=TaskStatus(row["status"]),
                    result=row["result"], error=row["error"],
                    created_at=row["created_at"], started_at=row["started_at"],
                    completed_at=row["completed_at"],
                )
                if not isinstance(task.id, str) or not task.id or not isinstance(task.prompt, str):
                    raise ValueError("Invalid saved task identity")
                if any(value is not None and not isinstance(value, str)
                       for value in (task.result, task.error)):
                    raise ValueError("Invalid saved task text")
                for value in (task.created_at, task.started_at, task.completed_at):
                    if value is not None and (
                        isinstance(value, bool) or not isinstance(value, (int, float))
                        or not isfinite(value)
                    ):
                        raise ValueError("Invalid saved task time")
            except (KeyError, IndexError, TypeError, ValueError):
                debug_log("saved task entry skipped: invalid record", "tasks")
                continue
            if task.status in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
                task.status = TaskStatus.FAILED
                task.error = "Task interrupted by daemon restart"
                task.completed_at = time.time()
                self._persist(task)
            self._tasks[task.id] = task
            self._cancel_events[task.id] = threading.Event()
            self._emit(task)
