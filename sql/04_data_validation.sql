-- ============================================================
-- 04_data_validation.sql
-- Leadership & Management Book Recommendation System
-- ============================================================
-- Purpose:
--   Perform comprehensive data-quality and relational-integrity
--   validation after the corrected Python dataset has been
--   loaded into MySQL.
--
-- Current validated dataset:
--   Canonical books:             2,067
--   Authors:                     2,281
--   Categories:                  2,187
--   Data sources:                    2
--   Book-author relationships:   2,566
--   Book-category relationships: 5,926
--   Book editions:               1,120
--   Book metric records:           950
--   Source records:              2,070
--
--   Total relational rows:      19,169
--
-- IMPORTANT:
--   This is a READ-ONLY validation script.
--   It does not INSERT, UPDATE, DELETE, DROP or TRUNCATE data.
-- ============================================================


USE leadership_books_db;


-- ============================================================
-- 1. CONFIRM ACTIVE DATABASE
-- ============================================================

SELECT
    DATABASE() AS active_database;


-- Expected:
-- leadership_books_db


-- ============================================================
-- 2. TABLE INVENTORY
-- ============================================================

SHOW TABLES;


-- Expected:
-- 9 tables


-- ============================================================
-- 3. EXPECTED ROW COUNTS
-- ============================================================

SELECT 'books' AS table_name, COUNT(*) AS row_count
FROM books

UNION ALL

SELECT 'authors', COUNT(*)
FROM authors

UNION ALL

SELECT 'categories', COUNT(*)
FROM categories

UNION ALL

SELECT 'data_sources', COUNT(*)
FROM data_sources

UNION ALL

SELECT 'book_authors', COUNT(*)
FROM book_authors

UNION ALL

SELECT 'book_categories', COUNT(*)
FROM book_categories

UNION ALL

SELECT 'book_editions', COUNT(*)
FROM book_editions

UNION ALL

SELECT 'book_metrics', COUNT(*)
FROM book_metrics

UNION ALL

SELECT 'source_records', COUNT(*)
FROM source_records;


-- Expected:
--
-- books                2067
-- authors              2281
-- categories           2187
-- data_sources            2
-- book_authors         2566
-- book_categories      5926
-- book_editions        1120
-- book_metrics          950
-- source_records       2070


-- ============================================================
-- 4. TOTAL RELATIONAL ROW COUNT
-- ============================================================

SELECT
      (SELECT COUNT(*) FROM books)
    + (SELECT COUNT(*) FROM authors)
    + (SELECT COUNT(*) FROM categories)
    + (SELECT COUNT(*) FROM data_sources)
    + (SELECT COUNT(*) FROM book_authors)
    + (SELECT COUNT(*) FROM book_categories)
    + (SELECT COUNT(*) FROM book_editions)
    + (SELECT COUNT(*) FROM book_metrics)
    + (SELECT COUNT(*) FROM source_records)
    AS total_relational_rows;


-- Expected:
-- 19169


-- ============================================================
-- 5. PRIMARY KEY UNIQUENESS
-- ============================================================

SELECT
    'books' AS table_name,
    COUNT(*) AS total_rows,
    COUNT(DISTINCT book_id) AS unique_ids,
    COUNT(*) - COUNT(DISTINCT book_id) AS duplicate_ids
FROM books

UNION ALL

SELECT
    'authors',
    COUNT(*),
    COUNT(DISTINCT author_id),
    COUNT(*) - COUNT(DISTINCT author_id)
FROM authors

UNION ALL

SELECT
    'categories',
    COUNT(*),
    COUNT(DISTINCT category_id),
    COUNT(*) - COUNT(DISTINCT category_id)
FROM categories

UNION ALL

SELECT
    'book_editions',
    COUNT(*),
    COUNT(DISTINCT edition_id),
    COUNT(*) - COUNT(DISTINCT edition_id)
FROM book_editions

UNION ALL

SELECT
    'data_sources',
    COUNT(*),
    COUNT(DISTINCT data_source_id),
    COUNT(*) - COUNT(DISTINCT data_source_id)
FROM data_sources

UNION ALL

SELECT
    'source_records',
    COUNT(*),
    COUNT(DISTINCT source_record_id),
    COUNT(*) - COUNT(DISTINCT source_record_id)
FROM source_records;


-- Expected:
-- duplicate_ids = 0 for every table


-- ============================================================
-- 6. DUPLICATE BOOK-AUTHOR RELATIONSHIPS
-- ============================================================

SELECT
    book_id,
    author_id,
    COUNT(*) AS duplicate_count

FROM book_authors

GROUP BY
    book_id,
    author_id

HAVING COUNT(*) > 1;


-- Expected:
-- 0 rows


-- ============================================================
-- 7. DUPLICATE BOOK-CATEGORY RELATIONSHIPS
-- ============================================================

SELECT
    book_id,
    category_id,
    COUNT(*) AS duplicate_count

FROM book_categories

GROUP BY
    book_id,
    category_id

HAVING COUNT(*) > 1;


-- Expected:
-- 0 rows


-- ============================================================
-- 8. REQUIRED BOOK FIELDS
-- ============================================================

SELECT
    SUM(
        CASE
            WHEN book_id IS NULL
              OR TRIM(book_id) = ''
            THEN 1 ELSE 0
        END
    ) AS missing_book_id,

    SUM(
        CASE
            WHEN title IS NULL
              OR TRIM(title) = ''
            THEN 1 ELSE 0
        END
    ) AS missing_title

FROM books;


-- Expected:
-- missing_book_id = 0
-- missing_title   = 0


-- ============================================================
-- 9. BOOK METADATA COVERAGE
-- ============================================================

SELECT
    COUNT(*) AS total_books,

    SUM(
        CASE
            WHEN description IS NOT NULL
             AND TRIM(description) <> ''
            THEN 1 ELSE 0
        END
    ) AS books_with_description,

    ROUND(
        100.0 *
        SUM(
            CASE
                WHEN description IS NOT NULL
                 AND TRIM(description) <> ''
                THEN 1 ELSE 0
            END
        ) / COUNT(*),
        2
    ) AS description_coverage_pct,

    SUM(
        CASE
            WHEN first_publish_year IS NOT NULL
            THEN 1 ELSE 0
        END
    ) AS books_with_first_publish_year,

    ROUND(
        100.0 *
        SUM(
            CASE
                WHEN first_publish_year IS NOT NULL
                THEN 1 ELSE 0
            END
        ) / COUNT(*),
        2
    ) AS first_publish_year_coverage_pct,

    SUM(
        CASE
            WHEN publication_year_observed IS NOT NULL
            THEN 1 ELSE 0
        END
    ) AS books_with_observed_year,

    ROUND(
        100.0 *
        SUM(
            CASE
                WHEN publication_year_observed IS NOT NULL
                THEN 1 ELSE 0
            END
        ) / COUNT(*),
        2
    ) AS observed_year_coverage_pct,

    SUM(
        CASE
            WHEN cover_url IS NOT NULL
             AND TRIM(cover_url) <> ''
            THEN 1 ELSE 0
        END
    ) AS books_with_cover,

    ROUND(
        100.0 *
        SUM(
            CASE
                WHEN cover_url IS NOT NULL
                 AND TRIM(cover_url) <> ''
                THEN 1 ELSE 0
            END
        ) / COUNT(*),
        2
    ) AS cover_coverage_pct

FROM books;


-- Known approximate coverage from integration:
--
-- description             192 / 2067 = 9.29%
-- first_publish_year      947 / 2067 = 45.82%
-- publication_year       1117 / 2067 = 54.04%
-- cover_url              1888 / 2067 = 91.34%
--
-- Sparse description coverage is expected and must NOT
-- be artificially imputed.


-- ============================================================
-- 10. AUTHOR COVERAGE
-- ============================================================

SELECT
    COUNT(*) AS total_books,

    COUNT(
        DISTINCT ba.book_id
    ) AS books_with_author,

    COUNT(*) -
    COUNT(
        DISTINCT ba.book_id
    ) AS books_without_author,

    ROUND(
        100.0 *
        COUNT(DISTINCT ba.book_id) /
        COUNT(*),
        2
    ) AS author_coverage_pct

FROM books AS b

LEFT JOIN book_authors AS ba
    ON b.book_id = ba.book_id;


-- Expected approximately:
-- books with authors = 2059
-- books without authors = 8
-- coverage = 99.61%


-- ============================================================
-- 11. CATEGORY COVERAGE
-- ============================================================

SELECT
    COUNT(*) AS total_books,

    COUNT(
        DISTINCT bc.book_id
    ) AS books_with_category,

    COUNT(*) -
    COUNT(
        DISTINCT bc.book_id
    ) AS books_without_category,

    ROUND(
        100.0 *
        COUNT(DISTINCT bc.book_id) /
        COUNT(*),
        2
    ) AS category_coverage_pct

FROM books AS b

LEFT JOIN book_categories AS bc
    ON b.book_id = bc.book_id;


-- Category sparsity is expected because LeadershipNow
-- does not provide the same subject structure as Open Library.


-- ============================================================
-- 12. METRIC COVERAGE
-- ============================================================

SELECT
    COUNT(*) AS total_books,

    COUNT(
        DISTINCT bm.book_id
    ) AS books_with_metrics,

    COUNT(*) -
    COUNT(
        DISTINCT bm.book_id
    ) AS books_without_metrics,

    ROUND(
        100.0 *
        COUNT(DISTINCT bm.book_id) /
        COUNT(*),
        2
    ) AS metric_coverage_pct

FROM books AS b

LEFT JOIN book_metrics AS bm
    ON b.book_id = bm.book_id;


-- Expected:
-- books_with_metrics = 950
-- coverage ≈ 45.96%


-- ============================================================
-- 13. NULL / INVALID AUTHOR VALUES
-- ============================================================

SELECT
    COUNT(*) AS invalid_author_records

FROM authors

WHERE author_name IS NULL
   OR TRIM(author_name) = ''
   OR author_normalized IS NULL
   OR TRIM(author_normalized) = '';


-- Expected:
-- 0


-- ============================================================
-- 14. NULL / INVALID CATEGORY VALUES
-- ============================================================

SELECT
    COUNT(*) AS invalid_category_records

FROM categories

WHERE category_name IS NULL
   OR TRIM(category_name) = ''
   OR category_normalized IS NULL
   OR TRIM(category_normalized) = '';


-- Expected:
-- 0


-- ============================================================
-- 15. NORMALIZED CATEGORY COLLISIONS
-- ============================================================
-- Multiple source labels may normalize to the same textual
-- representation. These are retained rather than silently
-- deleting source-derived category records.
-- ============================================================

SELECT
    category_normalized,
    COUNT(*) AS category_records

FROM categories

GROUP BY category_normalized

HAVING COUNT(*) > 1

ORDER BY category_records DESC,
         category_normalized;


-- This query is diagnostic.
-- Non-zero results are NOT automatically an error.


-- ============================================================
-- 16. NORMALIZED AUTHOR COLLISIONS
-- ============================================================

SELECT
    author_normalized,
    COUNT(*) AS author_records

FROM authors

GROUP BY author_normalized

HAVING COUNT(*) > 1

ORDER BY author_records DESC,
         author_normalized;


-- Diagnostic only.


-- ============================================================
-- 17. REFERENTIAL INTEGRITY:
-- BOOK_AUTHORS -> BOOKS
-- ============================================================

SELECT
    COUNT(*) AS orphan_book_author_books

FROM book_authors AS ba

LEFT JOIN books AS b
    ON ba.book_id = b.book_id

WHERE b.book_id IS NULL;


-- Expected: 0


-- ============================================================
-- 18. REFERENTIAL INTEGRITY:
-- BOOK_AUTHORS -> AUTHORS
-- ============================================================

SELECT
    COUNT(*) AS orphan_book_author_authors

FROM book_authors AS ba

LEFT JOIN authors AS a
    ON ba.author_id = a.author_id

WHERE a.author_id IS NULL;


-- Expected: 0


-- ============================================================
-- 19. REFERENTIAL INTEGRITY:
-- BOOK_CATEGORIES -> BOOKS
-- ============================================================

SELECT
    COUNT(*) AS orphan_book_category_books

FROM book_categories AS bc

LEFT JOIN books AS b
    ON bc.book_id = b.book_id

WHERE b.book_id IS NULL;


-- Expected: 0


-- ============================================================
-- 20. REFERENTIAL INTEGRITY:
-- BOOK_CATEGORIES -> CATEGORIES
-- ============================================================

SELECT
    COUNT(*) AS orphan_book_category_categories

FROM book_categories AS bc

LEFT JOIN categories AS c
    ON bc.category_id = c.category_id

WHERE c.category_id IS NULL;


-- Expected: 0


-- ============================================================
-- 21. REFERENTIAL INTEGRITY:
-- BOOK_EDITIONS -> BOOKS
-- ============================================================

SELECT
    COUNT(*) AS orphan_editions

FROM book_editions AS be

LEFT JOIN books AS b
    ON be.book_id = b.book_id

WHERE b.book_id IS NULL;


-- Expected: 0


-- ============================================================
-- 22. REFERENTIAL INTEGRITY:
-- BOOK_METRICS -> BOOKS
-- ============================================================

SELECT
    COUNT(*) AS orphan_metrics

FROM book_metrics AS bm

LEFT JOIN books AS b
    ON bm.book_id = b.book_id

WHERE b.book_id IS NULL;


-- Expected: 0


-- ============================================================
-- 23. REFERENTIAL INTEGRITY:
-- SOURCE_RECORDS -> BOOKS
-- ============================================================

SELECT
    COUNT(*) AS orphan_source_record_books

FROM source_records AS sr

LEFT JOIN books AS b
    ON sr.book_id = b.book_id

WHERE b.book_id IS NULL;


-- Expected: 0


-- ============================================================
-- 24. REFERENTIAL INTEGRITY:
-- SOURCE_RECORDS -> DATA_SOURCES
-- ============================================================

SELECT
    COUNT(*) AS orphan_source_record_sources

FROM source_records AS sr

LEFT JOIN data_sources AS ds
    ON sr.data_source_id = ds.data_source_id

WHERE ds.data_source_id IS NULL;


-- Expected: 0


-- ============================================================
-- 25. SOURCE FLAG VALIDATION
-- ============================================================

SELECT
    SUM(
        CASE
            WHEN source_openlibrary = 0
             AND source_leadershipnow = 0
            THEN 1 ELSE 0
        END
    ) AS books_without_source,

    SUM(
        CASE
            WHEN source_openlibrary = 1
             AND source_leadershipnow = 0
            THEN 1 ELSE 0
        END
    ) AS openlibrary_only,

    SUM(
        CASE
            WHEN source_openlibrary = 0
             AND source_leadershipnow = 1
            THEN 1 ELSE 0
        END
    ) AS leadershipnow_only,

    SUM(
        CASE
            WHEN source_openlibrary = 1
             AND source_leadershipnow = 1
            THEN 1 ELSE 0
        END
    ) AS both_sources

FROM books;


-- Expected:
--
-- books_without_source = 0
-- openlibrary_only     = 947
-- leadershipnow_only   = 1117
-- both_sources         = 3


-- ============================================================
-- 26. CONFIRMED CROSS-SOURCE BOOKS
-- ============================================================

SELECT
    book_id,
    title,
    source_openlibrary,
    source_leadershipnow

FROM books

WHERE source_openlibrary = 1
  AND source_leadershipnow = 1

ORDER BY title;


-- Expected:
--
-- BOOK00866 | Emotional Intelligence Habits
-- BOOK00036 | Leadership
-- BOOK00016 | The leadership challenge
--
-- Exactly 3 records


-- ============================================================
-- 27. CROSS-SOURCE COUNT
-- ============================================================

SELECT
    COUNT(*) AS confirmed_cross_source_books

FROM books

WHERE source_openlibrary = 1
  AND source_leadershipnow = 1;


-- Expected:
-- 3


-- ============================================================
-- 28. FALSE FUZZY MATCH CORRECTION
-- ============================================================
-- Team Emotional Intelligence 2.0 must remain separate from
-- Open Library's Emotional Intelligence 2.0.
-- ============================================================

SELECT
    b.book_id,
    b.title,

    GROUP_CONCAT(
        DISTINCT a.author_name
        ORDER BY a.author_name
        SEPARATOR '; '
    ) AS authors,

    b.source_openlibrary,
    b.source_leadershipnow,

    be.isbn_13,
    be.publication_year

FROM books AS b

LEFT JOIN book_authors AS ba
    ON b.book_id = ba.book_id

LEFT JOIN authors AS a
    ON ba.author_id = a.author_id

LEFT JOIN book_editions AS be
    ON b.book_id = be.book_id

WHERE b.book_id = 'BOOK01189'

GROUP BY
    b.book_id,
    b.title,
    b.source_openlibrary,
    b.source_leadershipnow,
    be.isbn_13,
    be.publication_year;


-- Expected:
--
-- BOOK01189
-- Team Emotional Intelligence 2.0
-- Jean Greaves and Evan Watkins
-- source_openlibrary    = 0
-- source_leadershipnow = 1
-- ISBN-13 = 9780974719344
-- year = 2022


-- ============================================================
-- 29. COMPARE EMOTIONAL INTELLIGENCE 2.0 ENTITIES
-- ============================================================

SELECT
    b.book_id,
    b.title,

    GROUP_CONCAT(
        DISTINCT a.author_name
        ORDER BY a.author_name
        SEPARATOR '; '
    ) AS authors,

    b.source_openlibrary,
    b.source_leadershipnow,

    be.isbn_13,
    be.publication_year

FROM books AS b

LEFT JOIN book_authors AS ba
    ON b.book_id = ba.book_id

LEFT JOIN authors AS a
    ON ba.author_id = a.author_id

LEFT JOIN book_editions AS be
    ON b.book_id = be.book_id

WHERE LOWER(b.title) LIKE '%emotional intelligence 2.0%'

GROUP BY
    b.book_id,
    b.title,
    b.source_openlibrary,
    b.source_leadershipnow,
    be.isbn_13,
    be.publication_year

ORDER BY b.title,
         b.book_id;


-- Used to verify that similarly titled books remain
-- distinct canonical entities when bibliographic evidence
-- does not support a merge.


-- ============================================================
-- 30. EDITION ID UNIQUENESS
-- ============================================================

SELECT
    COUNT(*) AS total_editions,
    COUNT(DISTINCT edition_id) AS unique_edition_ids,
    COUNT(*) - COUNT(DISTINCT edition_id)
        AS duplicate_edition_ids

FROM book_editions;


-- Expected:
-- total_editions = 1120
-- duplicate_edition_ids = 0


-- ============================================================
-- 31. SCRAPE ID UNIQUENESS
-- ============================================================

SELECT
    COUNT(*) AS total_editions,
    COUNT(DISTINCT scrape_id) AS unique_scrape_ids,
    COUNT(*) - COUNT(DISTINCT scrape_id)
        AS duplicate_scrape_ids

FROM book_editions;


-- Expected:
-- 1120 unique scrape IDs


-- ============================================================
-- 32. ISBN STATUS DISTRIBUTION
-- ============================================================

SELECT
    isbn_status,
    COUNT(*) AS edition_count,

    ROUND(
        100.0 * COUNT(*) /
        (SELECT COUNT(*) FROM book_editions),
        2
    ) AS percentage

FROM book_editions

GROUP BY isbn_status

ORDER BY edition_count DESC;


-- Diagnostic distribution.
-- Questionable source identifiers are preserved and labelled;
-- they are not fabricated or silently corrected.


-- ============================================================
-- 33. VALID ISBN-13 COVERAGE
-- ============================================================

SELECT
    COUNT(*) AS total_editions,

    SUM(
        CASE
            WHEN isbn_13 IS NOT NULL
             AND TRIM(isbn_13) <> ''
            THEN 1 ELSE 0
        END
    ) AS editions_with_isbn13,

    ROUND(
        100.0 *
        SUM(
            CASE
                WHEN isbn_13 IS NOT NULL
                 AND TRIM(isbn_13) <> ''
                THEN 1 ELSE 0
            END
        ) / COUNT(*),
        2
    ) AS isbn13_coverage_pct

FROM book_editions;


-- ============================================================
-- 34. DUPLICATE ISBN-13 DIAGNOSTIC
-- ============================================================
-- Multiple records with the same ISBN may reflect repeated
-- source listings rather than separate canonical works.
-- The raw-stage duplicate groups were preserved and resolved
-- during canonical integration.
-- ============================================================

SELECT
    isbn_13,
    COUNT(*) AS edition_records

FROM book_editions

WHERE isbn_13 IS NOT NULL
  AND TRIM(isbn_13) <> ''

GROUP BY isbn_13

HAVING COUNT(*) > 1

ORDER BY edition_records DESC,
         isbn_13;


-- Diagnostic only.


-- ============================================================
-- 35. PUBLICATION YEAR RANGE
-- ============================================================

SELECT
    MIN(first_publish_year)
        AS earliest_first_publish_year,

    MAX(first_publish_year)
        AS latest_first_publish_year,

    MIN(publication_year_observed)
        AS earliest_observed_publication_year,

    MAX(publication_year_observed)
        AS latest_observed_publication_year

FROM books;


-- Review for implausible years.


-- ============================================================
-- 36. POTENTIALLY INVALID BOOK YEARS
-- ============================================================

SELECT
    book_id,
    title,
    first_publish_year,
    publication_year_observed

FROM books

WHERE
    (
        first_publish_year IS NOT NULL
        AND (
            first_publish_year < 1000
            OR first_publish_year > YEAR(CURDATE()) + 1
        )
    )

    OR

    (
        publication_year_observed IS NOT NULL
        AND (
            publication_year_observed < 1000
            OR publication_year_observed > YEAR(CURDATE()) + 1
        )
    )

ORDER BY title;


-- Diagnostic.
-- Do not automatically modify records based only on this query.


-- ============================================================
-- 37. EDITION PUBLICATION YEAR RANGE
-- ============================================================

SELECT
    MIN(publication_year) AS earliest_edition_year,
    MAX(publication_year) AS latest_edition_year

FROM book_editions;


-- ============================================================
-- 38. POTENTIALLY INVALID EDITION YEARS
-- ============================================================

SELECT
    edition_id,
    book_id,
    publication_year,
    publisher

FROM book_editions

WHERE publication_year IS NOT NULL
  AND (
      publication_year < 1000
      OR publication_year > YEAR(CURDATE()) + 1
  )

ORDER BY publication_year;


-- Diagnostic only.


-- ============================================================
-- 39. METRIC VALUE VALIDATION
-- ============================================================

SELECT
    SUM(
        CASE
            WHEN average_rating < 0
              OR average_rating > 5
            THEN 1 ELSE 0
        END
    ) AS invalid_average_rating,

    SUM(
        CASE
            WHEN ratings_count < 0
            THEN 1 ELSE 0
        END
    ) AS negative_ratings_count,

    SUM(
        CASE
            WHEN edition_count < 0
            THEN 1 ELSE 0
        END
    ) AS negative_edition_count,

    SUM(
        CASE
            WHEN want_to_read_count < 0
            THEN 1 ELSE 0
        END
    ) AS negative_want_to_read,

    SUM(
        CASE
            WHEN currently_reading_count < 0
            THEN 1 ELSE 0
        END
    ) AS negative_currently_reading,

    SUM(
        CASE
            WHEN already_read_count < 0
            THEN 1 ELSE 0
        END
    ) AS negative_already_read

FROM book_metrics;


-- Expected:
-- all invalid/negative counts = 0


-- ============================================================
-- 40. METRIC NULL COVERAGE
-- ============================================================

SELECT
    COUNT(*) AS metric_records,

    SUM(
        CASE WHEN average_rating IS NULL
             THEN 1 ELSE 0 END
    ) AS missing_average_rating,

    SUM(
        CASE WHEN ratings_count IS NULL
             THEN 1 ELSE 0 END
    ) AS missing_ratings_count,

    SUM(
        CASE WHEN edition_count IS NULL
             THEN 1 ELSE 0 END
    ) AS missing_edition_count,

    SUM(
        CASE WHEN want_to_read_count IS NULL
             THEN 1 ELSE 0 END
    ) AS missing_want_to_read,

    SUM(
        CASE WHEN currently_reading_count IS NULL
             THEN 1 ELSE 0 END
    ) AS missing_currently_reading,

    SUM(
        CASE WHEN already_read_count IS NULL
             THEN 1 ELSE 0 END
    ) AS missing_already_read

FROM book_metrics;


-- Missing metrics remain NULL.
-- Do NOT replace unknown values with zero unless zero is
-- explicitly observed in the source.


-- ============================================================
-- 41. SOURCE RECORD DISTRIBUTION
-- ============================================================

SELECT
    ds.source_name,
    COUNT(*) AS source_record_count

FROM source_records AS sr

JOIN data_sources AS ds
    ON sr.data_source_id = ds.data_source_id

GROUP BY
    ds.data_source_id,
    ds.source_name

ORDER BY source_record_count DESC;


-- ============================================================
-- 42. SOURCE RECORD TYPE DISTRIBUTION
-- ============================================================

SELECT
    source_record_type,
    COUNT(*) AS record_count

FROM source_records

GROUP BY source_record_type

ORDER BY record_count DESC;


-- ============================================================
-- 43. MATCH METHOD DISTRIBUTION
-- ============================================================

SELECT
    COALESCE(match_method, 'Not Applicable')
        AS match_method,

    COUNT(*) AS record_count

FROM source_records

GROUP BY
    COALESCE(match_method, 'Not Applicable')

ORDER BY record_count DESC;


-- ============================================================
-- 44. MATCH CONFIDENCE DISTRIBUTION
-- ============================================================
-- match_confidence is categorical metadata and therefore
-- stored as VARCHAR rather than a numeric probability.
-- ============================================================

SELECT
    COALESCE(match_confidence, 'Not Applicable')
        AS match_confidence,

    COUNT(*) AS record_count

FROM source_records

GROUP BY
    COALESCE(match_confidence, 'Not Applicable')

ORDER BY record_count DESC;


-- ============================================================
-- 45. SOURCE RECORDS WITH INVALID BOOK REFERENCES
-- ============================================================

SELECT
    sr.source_record_id,
    sr.book_id,
    sr.data_source_id

FROM source_records AS sr

LEFT JOIN books AS b
    ON sr.book_id = b.book_id

WHERE b.book_id IS NULL;


-- Expected:
-- 0 rows


-- ============================================================
-- 46. SOURCE RECORDS WITH INVALID SOURCE REFERENCES
-- ============================================================

SELECT
    sr.source_record_id,
    sr.book_id,
    sr.data_source_id

FROM source_records AS sr

LEFT JOIN data_sources AS ds
    ON sr.data_source_id = ds.data_source_id

WHERE ds.data_source_id IS NULL;


-- Expected:
-- 0 rows


-- ============================================================
-- 47. BOOKS WITHOUT SOURCE RECORDS
-- ============================================================

SELECT
    b.book_id,
    b.title,
    b.source_openlibrary,
    b.source_leadershipnow

FROM books AS b

LEFT JOIN source_records AS sr
    ON b.book_id = sr.book_id

WHERE sr.book_id IS NULL

ORDER BY b.book_id;


-- Expected:
-- 0 rows


-- ============================================================
-- 48. NUMBER OF SOURCE RECORDS PER BOOK
-- ============================================================

SELECT
    source_record_count,
    COUNT(*) AS number_of_books

FROM
(
    SELECT
        b.book_id,
        COUNT(sr.source_record_id)
            AS source_record_count

    FROM books AS b

    LEFT JOIN source_records AS sr
        ON b.book_id = sr.book_id

    GROUP BY b.book_id
) AS source_counts

GROUP BY source_record_count

ORDER BY source_record_count;


-- Cross-source books should naturally have more than one
-- source record.


-- ============================================================
-- 49. BOOKS WITH MULTIPLE SOURCE RECORDS
-- ============================================================

SELECT
    b.book_id,
    b.title,
    COUNT(sr.source_record_id)
        AS source_record_count

FROM books AS b

JOIN source_records AS sr
    ON b.book_id = sr.book_id

GROUP BY
    b.book_id,
    b.title

HAVING COUNT(sr.source_record_id) > 1

ORDER BY
    source_record_count DESC,
    b.title;


-- Useful for auditing cross-source integration.


-- ============================================================
-- 50. FINAL QUALITY SUMMARY
-- ============================================================

SELECT

    (SELECT COUNT(*)
     FROM books)
        AS books,

    (SELECT COUNT(*)
     FROM authors)
        AS authors,

    (SELECT COUNT(*)
     FROM categories)
        AS categories,

    (SELECT COUNT(*)
     FROM book_editions)
        AS editions,

    (SELECT COUNT(*)
     FROM book_metrics)
        AS metric_records,

    (SELECT COUNT(*)
     FROM source_records)
        AS source_records,

    (
        SELECT COUNT(*)
        FROM books
        WHERE source_openlibrary = 1
          AND source_leadershipnow = 1
    ) AS confirmed_cross_source_books,

    (
        SELECT COUNT(*)
        FROM books
        WHERE source_openlibrary = 0
          AND source_leadershipnow = 0
    ) AS books_without_source,

    (
        SELECT COUNT(*)
        FROM book_editions AS be
        LEFT JOIN books AS b
            ON be.book_id = b.book_id
        WHERE b.book_id IS NULL
    ) AS orphan_editions,

    (
        SELECT COUNT(*)
        FROM source_records AS sr
        LEFT JOIN books AS b
            ON sr.book_id = b.book_id
        WHERE b.book_id IS NULL
    ) AS orphan_source_records;


-- ============================================================
-- EXPECTED CRITICAL FINAL VALUES
-- ============================================================
--
-- books                         = 2067
-- authors                       = 2281
-- categories                    = 2187
-- editions                      = 1120
-- metric_records                = 950
-- source_records                = 2070
-- confirmed_cross_source_books = 3
-- books_without_source          = 0
-- orphan_editions               = 0
-- orphan_source_records         = 0
--
-- ============================================================
-- END OF 04_data_validation.sql
-- ============================================================