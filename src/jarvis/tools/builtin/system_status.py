"""Read-only local system measurements for the ATLAS task executor.

This is a snapshot of system counters, NOT a hardware health diagnosis.
No network calls, AI inference, external commands, or file modifications.
"""

from __future__ import annotations

from math import isfinite
from pathlib import Path
from typing import Any, Dict, Optional

import psutil

from ..base import Tool, ToolContext
from ..types import ToolExecutionResult


class SystemStatusTool(Tool):
    """Collect CPU, RAM and home-drive capacity from the local machine."""

    @property
    def name(self) -> str:
        return "systemStatus"

    @property
    def description(self) -> str:
        return (
            "Measure local computer CPU usage, RAM usage and available disk "
            "space (home volume) without changing anything. Use when the user "
            "requests the current status of their own computer or a quick "
            "system diagnostic. This is not a GPU, thermal or hardware test."
        )

    @property
    def inputSchema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    def run(
        self, args: Optional[Dict[str, Any]], context: ToolContext,
    ) -> ToolExecutionResult:
        if args is not None and (not isinstance(args, dict) or args):
            return ToolExecutionResult(
                success=False,
                error_message="Le diagnostic système ne prend aucun paramètre.",
            )
        try:
            cpu = float(psutil.cpu_percent(interval=0.1))
            memory = psutil.virtual_memory()
            home = Path.home()
            volume = str(home.anchor or home)
            disk = psutil.disk_usage(volume)

            readings = (
                cpu, float(memory.percent), float(memory.used),
                float(memory.total), float(disk.free), float(disk.total),
            )
            if not all(isfinite(x) and x >= 0 for x in readings):
                raise ValueError("Compteurs système invalides")
            if memory.total <= 0 or disk.total <= 0:
                raise ValueError("Capacité système non disponible")

            gib = 1024 ** 3
            reply = (
                "Mesures locales actuelles (CPU : échantillon de 0,1 s) :\n"
                f"CPU utilisé : {cpu:.1f} %.\n"
                f"RAM utilisée : {memory.used / gib:.1f} / "
                f"{memory.total / gib:.1f} Gio ({memory.percent:.1f} %).\n"
                f"Espace libre sur le volume du profil ({volume}) : "
                f"{disk.free / gib:.1f} / {disk.total / gib:.1f} Gio.\n"
                "Ce relevé ne mesure ni GPU ni températures ; "
                "il ne prouve pas l'absence de panne matérielle."
            )
            return ToolExecutionResult(success=True, reply_text=reply)
        except Exception as exc:
            return ToolExecutionResult(
                success=False,
                error_message=(
                    "Impossible de relever les compteurs système : "
                    f"{type(exc).__name__}."
                ),
            )
