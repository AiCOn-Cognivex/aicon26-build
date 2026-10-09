"""Field schema shared by baselines, models, evaluation and the API."""
from __future__ import annotations

# Header (posting) fields -> CORD category used as the token label
HEADER_FIELDS = {
    "total": "total.total_price",
    "subtotal": "sub_total.subtotal_price",
    "tax": "sub_total.tax_price",
    "service_charge": "sub_total.service_price",
    "discount": "sub_total.discount_price",
}
# gt_parse location of each header field: (section, key)
HEADER_GT = {
    "total": ("total", "total_price"),
    "subtotal": ("sub_total", "subtotal_price"),
    "tax": ("sub_total", "tax_price"),
    "service_charge": ("sub_total", "service_price"),
    "discount": ("sub_total", "discount_price"),
}
ITEM_LABELS = {"menu.nm": "name", "menu.cnt": "qty", "menu.price": "price"}

DECISION_AUTO = "AUTO_POST"
DECISION_REVIEW = "HUMAN_REVIEW"
