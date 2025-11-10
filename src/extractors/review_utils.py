from typing import Any, Dict, Iterable, List, Optional
from statistics import mean
from collections import Counter
import re
thonimport logging

LOGGER = logging.getLogger(__name__)


def parse_product_id_from_url(url: str) -> str:
    """
    Extract the Target product ID from a product URL.

    Typical Target URLs look like:
    https://www.target.com/p/some-product-name/-/A-90171336

    We extract the numeric ID after "A-".
    """
    match = re.search(r"/A-(\d+)", url)
    if not match:
    raise ValueError(
        f"Unable to parse product ID from URL: {url!r}. "
        "Expected pattern '/A-'."
    )
    product_id = match.group(1)
    LOGGER.debug("Parsed product ID %s from URL %s", product_id, url)
    return product_id


def normalise_secondary_ratings(
    reviews: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Ensure that all reviews have a 'Secondary Ratings' list of
    {Label, Value} dictionaries. Also normalises various shapes
    (dicts, nested dicts, etc.) into a consistent format.
    """
    normalised: List[Dict[str, Any]] = []
    for review in reviews:
    sec = review.get("Secondary Ratings") or review.get("secondaryRatings")
    formatted: List[Dict[str, Any]] = []

    if isinstance(sec, list):
        # Already in desired format or close to it
    for item in sec:
    if isinstance(item, dict) and "Label" in item and "Value" in item:
    formatted.append(
        {"Label": str(item["Label"]), "Value": float(item["Value"])})
    elif isinstance(item, dict) and "label" in item and "value" in item:
    formatted.append(
        {"Label": str(item["label"]), "Value": float(item["value"])})
    elif isinstance(sec, dict):
        # Example: {"comfort": 4.5, "quality": 3, ...}
    for label, value in sec.items():
    try:
    formatted.append({"Label": str(label), "Value": float(value)})
    except Exception:  # noqa: BLE001
    continue

    review_copy = dict(review)
    review_copy["Secondary Ratings"] = formatted
    normalised.append(review_copy)

    return normalised


def build_product_summary(
    product_url: str,
    product_id: str,
    reviews: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build a product-level summary document from a list of reviews, matching
    the schema described in the project README.
    """
    if not reviews:
    raise ValueError("Cannot build summary from an empty review list.")

    ratings: List[int] = []
    recommended_count = 0
    not_recommended_count = 0

    # Some review feeds may store recommendation flags or booleans
    for review in reviews:
    rating = review.get("Rating")
    if isinstance(rating, (int, float)):
    ratings.append(int(rating))

    rec_flag = _extract_recommendation_flag(review)
    if rec_flag is True:
    recommended_count += 1
    elif rec_flag is False:
    not_recommended_count += 1

    rating_distribution: Dict[str, int] = {str(n): 0 for n in range(1, 6)}
    rating_counter = Counter(ratings)
    for k, v in rating_counter.items():
    if 1 = 4]
    positive_percentage = int(
        round(len(positive_ratings) / len(ratings) * 100)) if ratings else 0

        secondary_averages = _compute_secondary_averages(reviews)

    summary:
                Dict[str, Any] = {
    "Product URL": product_url,
    "Product ID": product_id,
    "Review Count": len(reviews),
    "Recommended Count": recommended_count,
    "Not Recommended Count": not_recommended_count,
    "Rating Distribution": rating_distribution,
    "Average Rating": round(avg_rating, 2),
    "Positive Percentage": positive_percentage,
    "Secondary Averages": secondary_averages,
    }
        return summary

        def _extract_recommendation_flag(review: Dict[str, Any]) -> Optional[bool]:
        """
    Attempt to infer whether the reviewer recommends the product.
    """
        for key in ("IsRecommended", "isRecommended", "recommended"):
        if key in review:
        value = review[key]
        if isinstance(value, bool):
        return value
        if isinstance(value, str):
        val_lower = value.strip().lower()
        if val_lower in {"yes", "true", "recommended"}:
        return True
        if val_lower in {"no", "false", "not recommended"}:
        return False

        # Some review feeds include a "recommendation" string field
        rec_text = review.get("Recommendation") or review.get("recommendation")
        if isinstance(rec_text, str):
        rec_lower = rec_text.strip().lower()
        if "would recommend" in rec_lower or rec_lower.startswith("yes"):
        return True
        if "would not recommend" in rec_lower or rec_lower.startswith("no"):
        return False

        return None

        def _compute_secondary_averages(
 reviews: List[Dict[str, Any]],


) -> List[Dict[str, Any]]:
    """
    Compute averages for secondary ratings (comfort, quality, sizing, style, etc.).
    """
    buckets: Dict[str, List[float]] = {}

    for review in reviews:
    secondary = review.get("Secondary Ratings") or []
    if not isinstance(secondary, list):
    continue

    for item in secondary:
    if not isinstance(item, dict):
    continue
    label = str(item.get("Label") or item.get("label") or "").strip().lower()
    if not label:
    continue
    value = item.get("Value") or item.get("value")
    try:
    numeric = float(value)
    except Exception:  # noqa: BLE001
    continue
    buckets.setdefault(label, []).append(numeric)

    averages: List[Dict[str, Any]] = []
    for label, values in buckets.items():
    if not values:
    continue
    averages.append(
  {
       "Label": label,
        "Value": round(mean(values), 2),
       }
   )

        return averages
