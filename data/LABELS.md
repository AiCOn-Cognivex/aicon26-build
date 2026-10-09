# Label set

Token labels are the CORD v2 categories with BIO tags. Categories with fewer than 10 annotated
entities in TRAIN are merged into their section's `.etc` label (or `O` if that is also rare).
Key accounting categories are never merged. The merge is computed on train only by `data/profile_cord.py`.

Kept: 23 categories. Merged: 6.

| original | train entities | merged into |
|---|---|---|
| menu.etc | 6 | O |
| menu.itemsubtotal | 1 | O |
| menu.vatyn | 2 | O |
| sub_total.othersvc_price | 2 | sub_total.etc |
| void_menu.nm | 1 | O |
| void_menu.price | 1 | O |
