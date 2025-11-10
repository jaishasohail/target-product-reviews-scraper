from outputs.json_exporter import JsonExporter
from extractors.review_utils import (
    parse_product_id_from_url,
    build_product_summary,
)
from extractors.target_parser import TargetReviewsScraper
from typing import List, Dict, Any, Optional
from pathlib import Path
import sys
import logging
import json
thonimport argparse


LOGGER = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )


def load_settings(config_path: Optional[Path]) -> Dict[str, Any]:
    """
    Load configuration from JSON file if it exists.
    Falls back to default settings if file is missing or invalid.
    """
    default_settings: Dict[str, Any] = {
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "request_timeout": 10,
        "max_reviews": None,
        "output_dir": "data",
        "output_prefix": "target_reviews_",
    }

    if config_path is None:
    LOGGER.info("No config path provided. Using default settings.")
    return default_settings

    if not config_path.exists():
    LOGGER.warning(
        "Config file %s not found. Using default settings.", config_path
    )
    return default_settings

    try:
    with config_path.open("r", encoding="utf-8") as f:
    loaded = json.load(f)
    if not isinstance(loaded, dict):
    raise ValueError("Config root must be a JSON object")
    merged = default_settings.copy()
    merged.update(loaded)
    LOGGER.info("Loaded configuration from %s", config_path)
    return merged
    except Exception as exc:
    LOGGER.error("Failed to load config from %s: %s", config_path, exc)
    LOGGER.info("Falling back to default settings.")
    return default_settings


def read_urls_from_file(path: Path) -> List[str]:
    """
    Read product URLs (one per line) from a text file.
    Empty lines and comments starting with '#' are ignored.
    """
    if not path.exists():
    raise FileNotFoundError(f"Input file not found: {path}")

    urls: List[str] = []
    with path.open("r", encoding="utf-8") as f:
    for line in f:
    line = line.strip()
    if not line or line.startswith("#"):
    continue
    urls.append(line)

    if not urls:
    raise ValueError(f"No URLs found in input file: {path}")

    return urls


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape product reviews from Target.com and export to JSON."
    )
    parser.add_argument(
        "urls",
        nargs="*",
        help="Target product URLs to scrape. "
        "If omitted, URLs will be read from data/sample_input.txt",
    )
    parser.add_argument(
        "-c",
        "--config",
        help="Path to configuration JSON file "
        "(defaults to src/config/settings.example.json)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        help="Directory to store output JSON files "
        "(overrides config setting if provided)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    setup_logging(verbose=args.verbose)

    project_root = Path(__file__).resolve().parents[1]
    default_config_path = project_root / "src" / "config" / "settings.example.json"
    config_path = Path(args.config).resolve(
    ) if args.config else default_config_path

    settings = load_settings(config_path)

    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else (project_root / settings.get("output_dir", "data"))
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    exporter = JsonExporter(base_dir=output_dir,
                            prefix=settings.get("output_prefix"))
    scraper = TargetReviewsScraper(
        user_agent=settings.get("user_agent"),
        timeout=settings.get("request_timeout", 10),
    )

    if args.urls:
    urls = args.urls
    else:
    sample_input = project_root / "data" / "sample_input.txt"
    LOGGER.info("No URLs provided. Reading from %s", sample_input)
    urls = read_urls_from_file(sample_input)

    overall_success = True

    for url in urls:
    LOGGER.info("Processing product URL: %s", url)
    try:
    product_id = parse_product_id_from_url(url)
    except ValueError as exc:
    LOGGER.error("Failed to extract product ID from URL '%s': %s", url, exc)
    overall_success = False
    continue

    try:
    reviews = scraper.fetch_reviews_for_product(
        product_url=url,
        product_id=product_id,
        max_reviews=settings.get("max_reviews"),
    )
    except Exception as exc:
    LOGGER.exception(
        "Failed to fetch reviews for product %s (%s): %s",
        product_id,
        url,
        exc,
    )
    overall_success = False
    continue

    if not reviews:
    LOGGER.warning(
        "No reviews found for product %s (%s). Skipping export.",
        product_id,
        url,
    )
    continue

    summary = build_product_summary(
        product_url=url,
        product_id=product_id,
        reviews=reviews,
    )

    combined: List[Dict[str, Any]] = [summary] + reviews
    output_path = exporter.generate_output_path(product_id=product_id)

    try:
    exporter.write_reviews_to_file(combined, output_path)
    LOGGER.info("Exported %d records to %s", len(combined), output_path)
    except Exception as exc:
    LOGGER.exception("Failed to export reviews for %s: %s", product_id, exc)
    overall_success = False

    return 0 if overall_success else 1


if __name__ == "__main__":
    sys.exit(main())
