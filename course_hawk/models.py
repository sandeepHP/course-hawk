import hashlib
from dataclasses import asdict, dataclass, field


@dataclass
class Course:
    """One course, filled in step by step: source -> verify -> filter.

    kind "coupon" = a paid Udemy course made free by a coupon (price is checked on Udemy).
    kind "free"   = a course that is always free (Microsoft Learn, YouTube, the curated catalog)."""

    url: str
    coupon: str = ""
    title: str = ""
    source: str = ""
    kind: str = "coupon"
    provider: str = "Udemy"
    certificate: str = ""  # e.g. "Free certificate"; empty when none or unknown
    # Filled in by the Udemy check.
    course_id: int | None = None
    headline: str = ""
    rating: float = 0.0
    num_reviews: int = 0
    students: int = 0
    hours: float = 0.0
    language: str = ""
    last_updated: str = ""  # "YYYY-MM-DD"
    instructor: str = ""
    list_price: float = 0.0
    price: float | None = None  # price with the coupon applied; None = unknown
    currency: str = "INR"
    expires_text: str = ""
    topics: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        if self.course_id:
            return str(self.course_id)
        # Short and stable: Telegram button data is limited to 64 bytes.
        return "u" + hashlib.sha1(self.url.split("?")[0].rstrip("/").encode()).hexdigest()[:12]

    @property
    def is_free(self) -> bool:
        if self.kind == "free":
            return True
        return self.price is not None and self.price == 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Course":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})
