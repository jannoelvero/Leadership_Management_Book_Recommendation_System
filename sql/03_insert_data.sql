-- ============================================================
-- 03_insert_data.sql
-- Leadership & Management Book Recommendation System
-- ============================================================
-- Purpose:
--   Verify the relational dataset loaded from Python/Jupyter
--   into MySQL.
--
-- IMPORTANT:
--   The project data is loaded programmatically from the
--   corrected pandas DataFrames using SQLAlchemy.
--
--   This script DOES NOT:
--      - create tables
--      - drop tables
--      - delete records
--      - truncate tables
--      - replace tables
--
-- Expected relational dataset:
--      9 tables
--      19,169 total rows
--      2,067 canonical books
-- ============================================================


USE leadership_books_db;


-- ============================================================
-- 1. VERIFY ACTIVE DATABASE
-- ============================================================

SELECT
    DATABASE() AS active_database;


-- ============================================================
-- 2. VERIFY REQUIRED TABLES EXIST
-- ============================================================

SHOW TABLES;


-- ============================================================
-- 3. ROW COUNTS BY TABLE
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


-- ============================================================
-- EXPECTED COUNTS
-- ============================================================
--
-- books                2,067
-- authors              2,281
-- categories           2,187
-- data_sources             2
-- book_authors         2,566
-- book_categories      5,926
-- book_editions        1,120
-- book_metrics           950
-- source_records       2,070
--
-- TOTAL               19,169
-- ============================================================


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
-- 19,169


-- ============================================================
-- 5. VERIFY DATA SOURCES
-- ============================================================

SELECT
    data_source_id,
    source_name,
    source_type,
    data_level
FROM data_sources
ORDER BY data_source_id;


-- Expected:
-- 2 source records


-- ============================================================
-- 6. VERIFY CANONICAL BOOK SOURCE COMPOSITION
-- ============================================================

SELECT
    CASE
        WHEN source_openlibrary = 1
         AND source_leadershipnow = 1
            THEN 'Both Sources'

        WHEN source_openlibrary = 1
         AND source_leadershipnow = 0
            THEN 'Open Library Only'

        WHEN source_openlibrary = 0
         AND source_leadershipnow = 1
            THEN 'LeadershipNow Only'

        ELSE 'Unknown'
    END AS source_group,

    COUNT(*) AS book_count

FROM books

GROUP BY source_group

ORDER BY book_count DESC;


-- Expected:
--
-- LeadershipNow Only : 1,117
-- Open Library Only  :   947
-- Both Sources       :     3
--
-- Total              : 2,067


-- ============================================================
-- 7. VERIFY EXACTLY THREE CROSS-SOURCE BOOKS
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


-- Expected cross-source canonical entities:
--
-- Emotional Intelligence Habits
-- Leadership
-- The Leadership Challenge
--
-- Expected count: 3


-- ============================================================
-- 8. CROSS-SOURCE COUNT
-- ============================================================

SELECT
    COUNT(*) AS confirmed_cross_source_books

FROM books

WHERE source_openlibrary = 1
  AND source_leadershipnow = 1;


-- Expected:
-- 3


-- ============================================================
-- 9. VERIFY TEAM EMOTIONAL INTELLIGENCE 2.0
-- ============================================================
-- This record was previously identified as a false fuzzy match.
-- It MUST remain a separate LeadershipNow-only canonical book.
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
-- book_id:
-- BOOK01189
--
-- title:
-- Team Emotional Intelligence 2.0
--
-- authors:
-- Jean Greaves and Evan Watkins
--
-- source_openlibrary:
-- 0
--
-- source_leadershipnow:
-- 1
--
-- ISBN-13:
-- 9780974719344
--
-- publication year:
-- 2022


-- ============================================================
-- 10. REFERENTIAL INTEGRITY:
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
-- 11. REFERENTIAL INTEGRITY:
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
-- 12. REFERENTIAL INTEGRITY:
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
-- 13. REFERENTIAL INTEGRITY:
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
-- 14. REFERENTIAL INTEGRITY:
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
-- 15. REFERENTIAL INTEGRITY:
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
-- 16. REFERENTIAL INTEGRITY:
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
-- 17. REFERENTIAL INTEGRITY:
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
-- 18. FINAL DATABASE SUMMARY
-- ============================================================

SELECT

    (SELECT COUNT(*) FROM books)
        AS books,

    (SELECT COUNT(*) FROM authors)
        AS authors,

    (SELECT COUNT(*) FROM categories)
        AS categories,

    (SELECT COUNT(*) FROM book_editions)
        AS editions,

    (SELECT COUNT(*) FROM book_metrics)
        AS metric_records,

    (SELECT COUNT(*) FROM source_records)
        AS source_records,

    (
        SELECT COUNT(*)
        FROM books
        WHERE source_openlibrary = 1
          AND source_leadershipnow = 1
    ) AS cross_source_books;


-- ============================================================
-- EXPECTED FINAL RESULT
-- ============================================================
--
-- books               = 2,067
-- authors             = 2,281
-- categories          = 2,187
-- editions            = 1,120
-- metric_records      =   950
-- source_records      = 2,070
-- cross_source_books  =     3
--
-- ============================================================
-- END OF 03_insert_data.sql
-- ============================================================