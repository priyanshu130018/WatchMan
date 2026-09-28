"""Application-wide numeric constants.

Single source of truth for pagination / collection sizing so that page-size
values are never scattered as magic numbers across routers, services, schemas,
and tests. Import these instead of hardcoding ``16``/``18``/``100``.
"""

from __future__ import annotations

# Standard catalogue page size. The desktop content grid is 6 columns x 3 rows,
# so a full page renders exactly 18 cards (page 1 = items 1-18, page 2 = 19-36…).
CONTENT_PAGE_SIZE = 18

# Hard cap for "popular" collections. The most-popular titles are exposed as a
# finite, paginated set: 100 items -> 6 pages of 18 (the last page holds 10).
# If fewer than this many valid items exist, the real (smaller) total is used.
POPULAR_COLLECTION_MAX = 100

# Trending is a single fixed-size showcase that is NEVER paginated: the top
# items (movies + web series combined) are shown on one page and capped here.
TRENDING_ITEMS = 18
