# Test cases: module 9 (Search)

Generated from one case list; 13 cases for 8 requirements (feedback 6, held-out 6, static 1). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-SRCH-01-a | LIB-SRCH-01 | Normal | Book `İstanbul Hatırası`; `q` = `ISTANBUL`, `istanbul`, `İstanbul` | Found with each query | feedback |
| T-SRCH-01-b | LIB-SRCH-01 | Boundary | Book `Işık Avcısı`; `q` = `işik`, `IŞIK`, `isik` | Found, found, not found (`ş` is not folded) | heldout |
| T-SRCH-02-a | LIB-SRCH-02 | Normal | `Kar` and `Kara Kitap` by Orhan Pamuk, `Kar Tanesi` by Ayşe Kulin; `q=kar pamuk` | Both Pamuk books, not `Kar Tanesi` (every token must match) | feedback |
| T-SRCH-02-b | LIB-SRCH-02 | Boundary | No `q`; `q` of spaces; `q` = the ISBN of one book | All 2 books; all 2 books; only that book | heldout |
| T-SRCH-03-a | LIB-SRCH-03 | Normal | Filters `author=pamuk`, `publisher=YAPI`, `language=en`, `year_from=2000&year_to=2005`, `classification_prefix=81`, combined | Each filter returns the matching books; combined filters are AND | feedback |
| T-SRCH-03-b | LIB-SRCH-03 | Error | `year_from=2010&year_to=2000` | `422 VALIDATION_ERROR` | heldout |
| T-SRCH-04-a | LIB-SRCH-04 | Normal | Book X: copy at A lent; book Y: copy available at B; `available_only=true`; with `branch_id=A`; `branch_id=B` alone | Y; none; Y | heldout |
| T-SRCH-05-a | LIB-SRCH-05 | Normal | `q=kar`: title `Kar`, author `Karl May`, publisher `Karınca`, title `Kar` by author `Karl May` (both) | Scores 3, 2, 1 and 3 (highest per token, not summed) | feedback |
| T-SRCH-05-b | LIB-SRCH-05 | Boundary | `q` = exact ISBN plus a title word; no `q` | 10 + 3 = 13; score 0 | heldout |
| T-SRCH-06-a | LIB-SRCH-06 | Normal | Sorts `relevance` (tie on score), `title`, `year_desc`, `year_asc` | Score then title; title; years descending and ascending with title as tie-breaker | feedback |
| T-SRCH-06-b | LIB-SRCH-06 | Normal | `sort=popularity`: book B lent twice (one returned), book A once, book C never | B, A, C; `loan_count` 2, 1, 0 | heldout |
| T-SRCH-07-a | LIB-SRCH-07 | Normal | 25 books; `page=2&page_size=10`; member searches | Paginated envelope (`total` 25, 10 items); each item has `book` (`BookOut`), `score`, `loan_count`; members may search | feedback |
| T-SRCH-08-a | LIB-SRCH-08 | Static | Workload W1 data set (100,000 books, 200,000 copies) | Results equal those of a reference filter over the same data (checked by the benchmark script) | static |
