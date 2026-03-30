import json
import random
from pathlib import Path
from models import (
    EpisodeConfig, DBSeed, CustomerRecord,
    OrderRecord, ProductRecord, OrderItem, ShippingAddress
)


class TicketGenerator:
    """Loads ticket configurations from a JSON file and serves them by task_id."""

    def __init__(self, tickets_path: Path) -> None:
        """Load and validate all ticket configs from *tickets_path*.

        Args:
            tickets_path: Path to the tickets JSON file.

        Raises:
            FileNotFoundError: If *tickets_path* does not exist.
            ValueError: If any ticket entry fails EpisodeConfig validation.
        """
        if not tickets_path.exists():
            raise FileNotFoundError(
                f"Tickets file not found: {tickets_path}"
            )

        raw_text = tickets_path.read_text(encoding="utf-8")
        raw_data = json.loads(raw_text)

        # Accept either a bare list or a dict wrapper {"tickets": [...]}
        if isinstance(raw_data, list):
            raw_tickets = raw_data
        elif isinstance(raw_data, dict) and "tickets" in raw_data:
            raw_tickets = raw_data["tickets"]
        else:
            raw_tickets = list(raw_data.values()) if isinstance(raw_data, dict) else []

        configs: list[EpisodeConfig] = []
        for idx, entry in enumerate(raw_tickets):
            try:
                configs.append(EpisodeConfig.model_validate(entry))
            except Exception as exc:
                ticket_id = entry.get("ticket_id", f"<index {idx}>") if isinstance(entry, dict) else f"<index {idx}>"
                raise ValueError(
                    f"Ticket '{ticket_id}' failed EpisodeConfig validation: {exc}"
                ) from exc

        self._configs: list[EpisodeConfig] = configs

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_config(self, task_id: str) -> EpisodeConfig:
        """Return an EpisodeConfig for *task_id*.

        If multiple configs share the same task_id, one is chosen at random
        to provide ticket variety across episodes.

        Args:
            task_id: The task identifier to look up.

        Raises:
            ValueError: If no config exists for *task_id*.
        """
        matches = [cfg for cfg in self._configs if cfg.task_id == task_id]
        if not matches:
            raise ValueError(f"Unknown task_id: {task_id}")
        if len(matches) == 1:
            return matches[0]
        return random.choice(matches)

    def list_task_ids(self) -> list[str]:
        """Return a sorted list of unique task_id strings across all loaded configs."""
        return sorted({cfg.task_id for cfg in self._configs})

    def list_configs(self) -> list[EpisodeConfig]:
        """Return a shallow copy of all loaded EpisodeConfig objects."""
        return list(self._configs)
