from .review_utils import normalise_secondary_ratings
import requests
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import time
import re
import logging
thonimport json


LOGGER = logging.getLogger(__name__)


@dataclass
class TargetReviewsScraper:
    """
    Scrapes review data for a single Target product.

    This implementation attempts to be resilient by:
    - Looking for embedded JSON objects in the product page HTML.
    - Falling back to a simple HTML review-card parser.
    """

    user_agent: str
    timeout: int = 10
    max_retries: int = 3
    backoff_factor: float = 0.5

    def __post_init__(self) -> None:
    self.session = requests.Session()
    self.session.headers.update({"User-Agent": self.user_agent})

    def _request_with_retry(self, url: str) -> requests.Response:
    last_exc: Optional[Exception] = None
    for attempt in range(1, self.max_retries + 1):
    try:
    LOGGER.debug("Fetching URL (attempt %d/%d): %s",
                 attempt, self.max_retries, url)
    resp = self.session.get(url, timeout=self.timeout)
    if resp.status_code >= 500:
    raise requests.HTTPError(
        f"Server error {resp.status_code} for URL {url}"
    )
    return resp
    except Exception as exc:  # noqa: BLE001
    last_exc = exc
    sleep_for = self.backoff_factor * (2 ** (attempt - 1))
    LOGGER.warning(
        "Request failed for %s (attempt %d/%d): %s. Retrying in %.1fs",
        url,
        attempt,
        self.max_retries,
        exc,
        sleep_for,
    )
    time.sleep(sleep_for)

    assert last_exc is not None
    raise last_exc

    def fetch_reviews_for_product(
        self,
        product_url: str,
        product_id: str,
        max_reviews: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
    """
 Fetch reviews for a product.

 Returns a list of review dictionaries with at least:
 - Product URL
 - Product ID
 - Review ID
 - Rating
 - Title
 - Text
 - Submitted Date
 - Helpful Votes
 - Unhelpful Votes
 - Author Nickname
 - Is Incentivized
 - Is Verified
 - Secondary Ratings (list of {Label, Value})
 """
    LOGGER.info("Fetching reviews for product %s", product_id)

    resp = self._request_with_retry(product_url)
    resp.raise_for_status()
    html = resp.text

    reviews = self._extract_reviews_from_embedded_json(
        html=html,
        product_url=product_url,
        product_id=product_id,
    )

    if not reviews:
    LOGGER.debug(
        "Embedded JSON reviews not found. Falling back to HTML parser.")
    reviews = self._extract_reviews_from_html(
        html=html,
        product_url=product_url,
        product_id=product_id,
    )

    if max_reviews is not None:
    reviews = reviews[:max_reviews]

    LOGGER.info("Fetched %d reviews for product %s", len(reviews), product_id)
    return reviews

    # -------------------------------------------------------------------------
    # Embedded JSON parsing
    # -------------------------------------------------------------------------

    def _extract_reviews_from_embedded_json(
        self,
        html: str,
        product_url: str,
        product_id: str,
    ) -> List[Dict[str, Any]]:
    """
 Many modern product pages embed a large JSON blob containing review data.
 This function scans for JSON-like blocks and attempts to parse review lists.
 """
    json_candidates = self._find_json_like_blobs(html)
    for candidate in json_candidates:
    try:
    data = json.loads(candidate)
    except Exception:
    continue

    reviews = self._find_reviews_in_json_tree(
        data=data,
        product_url=product_url,
        product_id=product_id,
    )
    if reviews:
    return reviews

    return []

    def _find_json_like_blobs(self, html: str) -> List[str]:
    """
 Extract JSON-like blobs from the HTML source.
 This is intentionally permissive and may parse multiple blobs.
 """
    blobs: List[str] = []

    # Common pattern: ... JSON ...
    script_pattern = re.compile(
        r"]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)",
        re.DOTALL | re.IGNORECASE,
    )
    for match in script_pattern.finditer(html):
    script_content = match.group(1).strip()
    if script_content:
    blobs.append(script_content)

    # Fallback: look for JSON objects starting with '{' followed by "reviews"
    loose_pattern = re.compile(
        r"\{[^{}]*(\"reviews\"|\"review\")[:\[][^{}]*\}", re.DOTALL)
    for match in loose_pattern.finditer(html):
    blobs.append(match.group(0))

    LOGGER.debug("Found %d JSON-like blobs in HTML", len(blobs))
    return blobs

    def _find_reviews_in_json_tree(
        self,
        data: Any,
        product_url: str,
        product_id: str,
    ) -> List[Dict[str, Any]]:
    """
 Recursively search for review-like structures inside a JSON tree.
 """
    collected: List[Dict[str, Any]] = []

    def visit(node: Any) -> None:
    if isinstance(node, dict):
    keys = set(node.keys())
    # Heuristic: review object
    required_keys = {"reviewBody", "reviewRating", "datePublished"}
    if required_keys.issubset(keys):
    collected.append(self._convert_json_review(node, product_url, product_id))
    for value in node.values():
    visit(value)
    elif isinstance(node, list):
    for item in node:
    visit(item)

    visit(data)
    collected = normalise_secondary_ratings(collected)
    return collected

    def _convert_json_review(
        self,
        node: Dict[str, Any],
        product_url: str,
        product_id: str,
    ) -> Dict[str, Any]:
    """
 Convert a generic JSON-LD review node into the unified review schema.
 """
    rating_value = None
    if isinstance(node.get("reviewRating"), dict):
    rating_value = node["reviewRating"].get("ratingValue")

    # Fallback for different property names
    rating_value = rating_value or node.get(
        "rating") or node.get("ratingValue")

    try:
    rating = int(rating_value)
    except Exception:
    rating = None

    author = node.get("author")
    if isinstance(author, dict):
    author_name = author.get("name") or ""
    else:
    author_name = str(author or "")

    review_id = node.get("@id") or node.get("reviewId") or node.get("id") or ""

    review: Dict[str, Any] = {
        "Product URL": product_url,
        "Product ID": product_id,
        "Review ID": review_id,
        "Rating": rating,
        "Title": node.get("name") or node.get("headline") or "",
        "Text": node.get("reviewBody") or "",
        "Submitted Date": node.get("datePublished") or "",
        "Helpful Votes": node.get("upvoteCount") or 0,
        "Unhelpful Votes": node.get("downvoteCount") or 0,
        "Author Nickname": author_name,
        "Is Incentivized": bool(node.get("isSponsored") or node.get("isIncentivized", False)),
        "Is Verified": bool(node.get("isVerified") or node.get("verifiedPurchase", False)),
        "Secondary Ratings": [],
        "Photos": [],
        "Client Responses": [],
    }

    # Optional: embedded images
    images = []
    for key in ("image", "photos", "reviewMedia"):
    media = node.get(key)
    if isinstance(media, list):
    for item in media:
    if isinstance(item, dict) and item.get("url"):
    images.append(item["url"])
    elif isinstance(item, str):
    images.append(item)
    elif isinstance(media, dict) and media.get("url"):
    images.append(media["url"])
    if images:
    review["Photos"] = images

    # Optional: merchant responses
    responses = node.get("publisherResponse") or node.get("sellerResponses")
    if isinstance(responses, list):
    review["Client Responses"] = responses
    elif isinstance(responses, dict):
    review["Client Responses"] = [responses]

    return review

    # -------------------------------------------------------------------------
    # HTML parsing fallback
    # -------------------------------------------------------------------------

    def _extract_reviews_from_html(
        self,
        html: str,
        product_url: str,
        product_id: str,
    ) -> List[Dict[str, Any]]:
    """
 Very simple HTML parser looking for review cards. This is a heuristic-based
 fallback and may not capture all reviews, but keeps the scraper functional
 if embedded JSON is missing.
 """
    try:
    from bs4 import BeautifulSoup  # type: ignore
    except Exception as exc:  # noqa: BLE001
    LOGGER.error(
        "BeautifulSoup is required for HTML parsing fallback but is not installed: %s",
        exc,
    )
    return []

    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all(attrs={"data-test": re.compile(".*review.*", re.I)})

    reviews: List[Dict[str, Any]] = []
    for idx, card in enumerate(cards, start=1):
    title_el = card.find(["h3", "h4"])
    title = title_el.get_text(strip=True) if title_el else ""

    text_el = card.find("p")
    text = text_el.get_text(strip=True) if text_el else ""

    rating_el = card.find(
        attrs={"aria-label": re.compile("out of 5 stars", re.I)})
    rating = None
    if rating_el and rating_el.get("aria-label"):
    m = re.search(r"(\d+(?:\.\d+)?)\s+out of 5", rating_el["aria-label"])
    if m:
    try:
    rating = int(round(float(m.group(1))))
    except Exception:
    rating = None

    date_el = card.find("time")
    date_text = date_el.get("datetime") or date_el.get_text(
        strip=True) if date_el else ""

    author_el = card.find(
        attrs={"data-test": re.compile(".*reviewer.*", re.I)})
    author_name = author_el.get_text(strip=True) if author_el else ""

    review = {
        "Product URL": product_url,
        "Product ID": product_id,
        "Review ID": f"html-{idx}",
        "Rating": rating,
        "Title": title,
        "Text": text,
        "Submitted Date": date_text,
        "Helpful Votes": 0,
        "Unhelpful Votes": 0,
        "Author Nickname": author_name,
        "Is Incentivized": False,
        "Is Verified": False,
        "Secondary Ratings": [],
        "Photos": [],
        "Client Responses": [],
    }
    reviews.append(review)

    reviews = normalise_secondary_ratings(reviews)
    return reviews
