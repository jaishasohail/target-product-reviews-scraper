from typing import Any, Dict, Iterable, List, Optional
from pathlib import Path
import logging
thonimport json

LOGGER = logging.getLogger(__name__)


class JsonExporter:
    """
    Handles exporting review data to JSON files.
    """

    def __init__(self, base_dir: Path, prefix: Optional[str] = None) -> None:
    self.base_dir = Path(base_dir)
    self.prefix = prefix or "reviews_"
    self.base_dir.mkdir(parents=True, exist_ok=True)
    LOGGER.debug("JsonExporter initialised with base_dir=%s prefix=%s",
                 self.base_dir, self.prefix)

    def generate_output_path(self, product_id: str) -> Path:
    filename = f"{self.prefix}{product_id}.json"
    path = self.base_dir / filename
    LOGGER.debug("Generated output path %s for product %s", path, product_id)
    return path

    def write_reviews_to_file(
        self,
        reviews: Iterable[Dict[str, Any]],
        output_path: Path,
        indent: int = 2,
    ) -> None:
    """
 Serialize reviews to JSON and write them to file.
 Existing files will be overwritten.
 """
    data_list: List[Dict[str, Any]] = list(reviews)

    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    LOGGER.debug("Writing %d records to temp file %s",
                 len(data_list), tmp_path)

    try:
    with tmp_path.open("w", encoding="utf-8") as f:
    json.dump(data_list, f, ensure_ascii=False, indent=indent)

    tmp_path.replace(output_path)
    LOGGER.info("Successfully wrote JSON output to %s", output_path)
    finally:
    if tmp_path.exists():
        # If replace failed for some reason, ensure we don't leave a stale temp file
    if tmp_path != output_path:
    try:
    tmp_path.unlink()
    except Exception:  # noqa: BLE001
    LOGGER.debug("Failed to clean up temp file %s", tmp_path)
