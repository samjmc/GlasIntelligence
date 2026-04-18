"""
Task state management.
Tracks long-running tasks such as graph builds and simulations.
"""

import uuid
import threading
from datetime import datetime
from enum import Enum
from typing import Any
from dataclasses import dataclass, field


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Task:
    task_id: str
    task_type: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    progress: int = 0
    message: str = ""
    result: dict | None = None
    error: str | None = None
    metadata: dict = field(default_factory=dict)
    progress_detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "progress": self.progress,
            "message": self.message,
            "progress_detail": self.progress_detail,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }


class TaskManager:
    """Thread-safe singleton task state manager."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._tasks: dict[str, Task] = {}
                    cls._instance._task_lock = threading.Lock()
        return cls._instance

    def create_task(self, task_type: str, metadata: dict | None = None) -> str:
        task_id = str(uuid.uuid4())
        now = datetime.now()

        task = Task(
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )

        with self._task_lock:
            self._tasks[task_id] = task

        return task_id

    def get_task(self, task_id: str) -> Task | None:
        with self._task_lock:
            return self._tasks.get(task_id)

    def update_task(
        self,
        task_id: str,
        status: TaskStatus | None = None,
        progress: int | None = None,
        message: str | None = None,
        result: dict | None = None,
        error: str | None = None,
        progress_detail: dict | None = None,
    ):
        with self._task_lock:
            task = self._tasks.get(task_id)
            if task:
                task.updated_at = datetime.now()
                if status is not None:
                    task.status = status
                if progress is not None:
                    task.progress = progress
                if message is not None:
                    task.message = message
                if result is not None:
                    task.result = result
                if error is not None:
                    task.error = error
                if progress_detail is not None:
                    task.progress_detail = progress_detail

    def complete_task(self, task_id: str, result: dict):
        self.update_task(task_id, status=TaskStatus.COMPLETED, progress=100, message="Task complete", result=result)

    def fail_task(self, task_id: str, error: str):
        self.update_task(task_id, status=TaskStatus.FAILED, message="Task failed", error=error)

    def list_tasks(self, task_type: str | None = None) -> list:
        with self._task_lock:
            tasks = list(self._tasks.values())
            if task_type:
                tasks = [t for t in tasks if t.task_type == task_type]
            return [t.to_dict() for t in sorted(tasks, key=lambda x: x.created_at, reverse=True)]

    def cleanup_old_tasks(self, max_age_hours: int = 24):
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(hours=max_age_hours)

        with self._task_lock:
            old_ids = [
                tid
                for tid, task in self._tasks.items()
                if task.created_at < cutoff and task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]
            ]
            for tid in old_ids:
                del self._tasks[tid]
