-- ============================================================
-- 05_analysis_queries.sql
-- Leadership & Management Book Recommendation System
-- ============================================================
-- Purpose:
--   Perform exploratory and business-oriented SQL analysis
--   on the final integrated book database.
--
-- Final validated database:
--   Books:                       2,067
--   Authors:                     2,281
--   Categories:                  2,187
--   Book-author relationships:   2,566
--   Book-category relationships: 5,926
--   Editions:                    1,120
--   Metric records:                950
--   Source records:              2,070
--   Confirmed cross-source books:    3
--
-- IMPORTANT:
--   READ-ONLY ANALYTICAL SCRIPT.
-- ============================================================


USE leadership_books_db;


-- ============================================================
-- 1. DATABASE OVERVIEW
-- ============================================================

SELECT
    (SELECT COUNT(*) FROM books) AS total_books,
    (SELECT COUNT(*) FROM authors) AS total_authors,
    (SELECT COUNT(*) FROM categories) AS total_categories,
    (SELECT COUNT(*) FROM book_authors) AS book_author_relationships,
    (SELECT COUNT(*) FROM book_categories) AS book_category_relationships,
    (SELECT COUNT(*) FROM book_editions) AS total_editions,
    (SELECT COUNT(*) FROM book_metrics) AS metric_records,
    (SELECT COUNT(*) FROM source_records) AS source_records;


-- Expected:
-- 2067 | 2281 | 2187 | 2566 | 5926 | 1120 | 950 | 2070


-- ============================================================
-- 2. BOOK DISTRIBUTION BY SOURCE
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

    COUNT(*) AS book_count,

    ROUND(
        100.0 * COUNT(*) /
        (SELECT COUNT(*) FROM books),
        2
    ) AS percentage_of_books

FROM books

GROUP BY source_group

ORDER BY book_count DESC;


-- Expected:
-- LeadershipNow Only = 1117
-- Open Library Only  = 947
-- Both Sources       = 3


-- ============================================================
-- 3. CONFIRMED CROSS-SOURCE BOOKS
-- ============================================================

SELECT
    book_id,
    title,
    first_publish_year,
    publication_year_observed,
    source_openlibrary,
    source_leadershipnow

FROM books

WHERE source_openlibrary = 1
  AND source_leadershipnow = 1

ORDER BY title;


-- Expected exactly 3 canonical books.


-- ============================================================
-- 4. FIRST PUBLICATION YEAR DISTRIBUTION
-- ============================================================

SELECT
    first_publish_year,
    COUNT(*) AS book_count

FROM books

WHERE first_publish_year IS NOT NULL

GROUP BY first_publish_year

ORDER BY first_publish_year;


-- ============================================================
-- 5. MOST COMMON FIRST PUBLICATION YEARS
-- ============================================================

SELECT
    first_publish_year,
    COUNT(*) AS book_count

FROM books

WHERE first_publish_year IS NOT NULL

GROUP BY first_publish_year

ORDER BY
    book_count DESC,
    first_publish_year DESC

LIMIT 20;


-- ============================================================
-- 6. OBSERVED PUBLICATION YEAR DISTRIBUTION
-- ============================================================

SELECT
    publication_year_observed,
    COUNT(*) AS book_count

FROM books

WHERE publication_year_observed IS NOT NULL

GROUP BY publication_year_observed

ORDER BY publication_year_observed;


-- ============================================================
-- 7. LEADERSHIPNOW EDITIONS BY PUBLICATION YEAR
-- ============================================================

SELECT
    publication_year,
    COUNT(*) AS edition_count

FROM book_editions

WHERE publication_year IS NOT NULL

GROUP BY publication_year

ORDER BY publication_year;


-- ============================================================
-- 8. BOOKS BY DECADE
-- ============================================================

SELECT
    FLOOR(first_publish_year / 10) * 10
        AS publication_decade,

    COUNT(*) AS book_count

FROM books

WHERE first_publish_year IS NOT NULL

GROUP BY publication_decade

ORDER BY publication_decade;


-- ============================================================
-- 9. TOP AUTHORS BY NUMBER OF BOOKS
-- ============================================================

SELECT
    a.author_id,
    a.author_name,

    COUNT(DISTINCT ba.book_id)
        AS number_of_books

FROM authors AS a

JOIN book_authors AS ba
    ON a.author_id = ba.author_id

GROUP BY
    a.author_id,
    a.author_name

ORDER BY
    number_of_books DESC,
    a.author_name

LIMIT 25;


-- ============================================================
-- 10. BOOKS WITH MULTIPLE AUTHORS
-- ============================================================

SELECT
    b.book_id,
    b.title,

    COUNT(DISTINCT ba.author_id)
        AS author_count

FROM books AS b

JOIN book_authors AS ba
    ON b.book_id = ba.book_id

GROUP BY
    b.book_id,
    b.title

HAVING COUNT(DISTINCT ba.author_id) > 1

ORDER BY
    author_count DESC,
    b.title

LIMIT 50;


-- ============================================================
-- 11. AUTHORSHIP DISTRIBUTION
-- ============================================================

SELECT
    author_count,
    COUNT(*) AS number_of_books

FROM
(
    SELECT
        b.book_id,
        COUNT(DISTINCT ba.author_id)
            AS author_count

    FROM books AS b

    LEFT JOIN book_authors AS ba
        ON b.book_id = ba.book_id

    GROUP BY b.book_id

) AS author_counts

GROUP BY author_count

ORDER BY author_count;


-- ============================================================
-- 12. MOST FREQUENT SOURCE CATEGORIES
-- ============================================================

SELECT
    c.category_id,
    c.category_name,

    COUNT(DISTINCT bc.book_id)
        AS number_of_books

FROM categories AS c

JOIN book_categories AS bc
    ON c.category_id = bc.category_id

GROUP BY
    c.category_id,
    c.category_name

ORDER BY
    number_of_books DESC,
    c.category_name

LIMIT 30;


-- NOTE:
-- These are source-derived categories/subjects.
-- They are not NLP topics or ML clusters.


-- ============================================================
-- 13. CATEGORY COUNT PER BOOK DISTRIBUTION
-- ============================================================

SELECT
    category_count,
    COUNT(*) AS number_of_books

FROM
(
    SELECT
        b.book_id,

        COUNT(DISTINCT bc.category_id)
            AS category_count

    FROM books AS b

    LEFT JOIN book_categories AS bc
        ON b.book_id = bc.book_id

    GROUP BY b.book_id

) AS category_counts

GROUP BY category_count

ORDER BY category_count;


-- ============================================================
-- 14. BOOKS WITH THE MOST SOURCE CATEGORIES
-- ============================================================

SELECT
    b.book_id,
    b.title,

    COUNT(DISTINCT bc.category_id)
        AS category_count

FROM books AS b

JOIN book_categories AS bc
    ON b.book_id = bc.book_id

GROUP BY
    b.book_id,
    b.title

ORDER BY
    category_count DESC,
    b.title

LIMIT 25;


-- ============================================================
-- 15. LEADERSHIP-RELATED SOURCE CATEGORIES
-- ============================================================

SELECT
    c.category_name,

    COUNT(DISTINCT bc.book_id)
        AS number_of_books

FROM categories AS c

JOIN book_categories AS bc
    ON c.category_id = bc.category_id

WHERE LOWER(c.category_name)
      LIKE '%leadership%'

GROUP BY
    c.category_id,
    c.category_name

ORDER BY
    number_of_books DESC,
    c.category_name;


-- ============================================================
-- 16. MANAGEMENT-RELATED SOURCE CATEGORIES
-- ============================================================

SELECT
    c.category_name,

    COUNT(DISTINCT bc.book_id)
        AS number_of_books

FROM categories AS c

JOIN book_categories AS bc
    ON c.category_id = bc.category_id

WHERE LOWER(c.category_name)
      LIKE '%management%'

GROUP BY
    c.category_id,
    c.category_name

ORDER BY
    number_of_books DESC,
    c.category_name;


-- ============================================================
-- 17. METRIC AND RATING AVAILABILITY
-- ============================================================

SELECT
    COUNT(*) AS metric_records,

    COUNT(average_rating)
        AS records_with_average_rating,

    COUNT(ratings_count)
        AS records_with_ratings_count,

    ROUND(
        100.0 * COUNT(average_rating) / COUNT(*),
        2
    ) AS rating_availability_pct

FROM book_metrics;


-- Important:
-- 950 metric records does NOT mean 950 books have ratings.
-- Missing rating values remain NULL.


-- ============================================================
-- 18. AVERAGE RATING SUMMARY
-- ============================================================

SELECT
    COUNT(average_rating)
        AS books_with_rating,

    ROUND(AVG(average_rating), 2)
        AS mean_rating,

    ROUND(MIN(average_rating), 2)
        AS minimum_rating,

    ROUND(MAX(average_rating), 2)
        AS maximum_rating

FROM book_metrics

WHERE average_rating IS NOT NULL;


-- ============================================================
-- 19. RATING DISTRIBUTION
-- ============================================================

SELECT
    CASE
        WHEN average_rating < 1
            THEN '0.00-0.99'

        WHEN average_rating < 2
            THEN '1.00-1.99'

        WHEN average_rating < 3
            THEN '2.00-2.99'

        WHEN average_rating < 4
            THEN '3.00-3.99'

        ELSE '4.00-5.00'
    END AS rating_band,

    COUNT(*) AS book_count

FROM book_metrics

WHERE average_rating IS NOT NULL

GROUP BY rating_band

ORDER BY rating_band;


-- ============================================================
-- 20. HIGHEST OBSERVED RATINGS
--     WITH AT LEAST 100 RATINGS
-- ============================================================

SELECT
    b.book_id,
    b.title,
    bm.average_rating,
    bm.ratings_count

FROM books AS b

JOIN book_metrics AS bm
    ON b.book_id = bm.book_id

WHERE bm.average_rating IS NOT NULL
  AND bm.ratings_count IS NOT NULL
  AND bm.ratings_count >= 100

ORDER BY
    bm.average_rating DESC,
    bm.ratings_count DESC

LIMIT 25;


-- This is a dataset-derived analytical shortlist.
-- It is NOT an objective ranking of the "best" books.


-- ============================================================
-- 21. MOST-RATED BOOKS
-- ============================================================

SELECT
    b.book_id,
    b.title,
    bm.average_rating,
    bm.ratings_count

FROM books AS b

JOIN book_metrics AS bm
    ON b.book_id = bm.book_id

WHERE bm.ratings_count IS NOT NULL

ORDER BY
    bm.ratings_count DESC,
    bm.average_rating DESC

LIMIT 25;


-- ============================================================
-- 22. MOST WANTED-TO-READ BOOKS
-- ============================================================

SELECT
    b.book_id,
    b.title,
    bm.want_to_read_count,
    bm.average_rating,
    bm.ratings_count

FROM books AS b

JOIN book_metrics AS bm
    ON b.book_id = bm.book_id

WHERE bm.want_to_read_count IS NOT NULL

ORDER BY
    bm.want_to_read_count DESC

LIMIT 25;


-- ============================================================
-- 23. MOST CURRENTLY-READING BOOKS
-- ============================================================

SELECT
    b.book_id,
    b.title,
    bm.currently_reading_count,
    bm.want_to_read_count,
    bm.ratings_count

FROM books AS b

JOIN book_metrics AS bm
    ON b.book_id = bm.book_id

WHERE bm.currently_reading_count IS NOT NULL

ORDER BY
    bm.currently_reading_count DESC

LIMIT 25;


-- ============================================================
-- 24. MOST ALREADY-READ BOOKS
-- ============================================================

SELECT
    b.book_id,
    b.title,
    bm.already_read_count,
    bm.average_rating,
    bm.ratings_count

FROM books AS b

JOIN book_metrics AS bm
    ON b.book_id = bm.book_id

WHERE bm.already_read_count IS NOT NULL

ORDER BY
    bm.already_read_count DESC

LIMIT 25;


-- ============================================================
-- 25. READER ENGAGEMENT SUMMARY
-- ============================================================

SELECT
    ROUND(AVG(ratings_count), 2)
        AS avg_ratings_count,

    MAX(ratings_count)
        AS max_ratings_count,

    ROUND(AVG(want_to_read_count), 2)
        AS avg_want_to_read,

    MAX(want_to_read_count)
        AS max_want_to_read,

    ROUND(AVG(currently_reading_count), 2)
        AS avg_currently_reading,

    MAX(currently_reading_count)
        AS max_currently_reading,

    ROUND(AVG(already_read_count), 2)
        AS avg_already_read,

    MAX(already_read_count)
        AS max_already_read

FROM book_metrics;


-- ============================================================
-- 26. RATING VS RATING VOLUME DATA
-- ============================================================

SELECT
    b.book_id,
    b.title,
    bm.average_rating,
    bm.ratings_count

FROM books AS b

JOIN book_metrics AS bm
    ON b.book_id = bm.book_id

WHERE bm.average_rating IS NOT NULL
  AND bm.ratings_count IS NOT NULL

ORDER BY bm.ratings_count DESC;


-- This dataset can later be used in Python for:
-- correlation analysis
-- scatter plots
-- log transformations
-- outlier analysis
--
-- SQL is used here for extraction only.
-- No causal relationship is implied.


-- ============================================================
-- 27. MOST COMMON PUBLISHERS
-- ============================================================

SELECT
    publisher,

    COUNT(*) AS edition_count,

    COUNT(DISTINCT book_id)
        AS distinct_books

FROM book_editions

WHERE publisher IS NOT NULL
  AND TRIM(publisher) <> ''

GROUP BY publisher

ORDER BY
    distinct_books DESC,
    edition_count DESC,
    publisher

LIMIT 30;


-- ============================================================
-- 28. EDITION FORMAT DISTRIBUTION
-- ============================================================

SELECT
    COALESCE(
        NULLIF(TRIM(format), ''),
        'Unknown'
    ) AS edition_format,

    COUNT(*) AS edition_count,

    ROUND(
        100.0 * COUNT(*) /
        (SELECT COUNT(*) FROM book_editions),
        2
    ) AS percentage

FROM book_editions

GROUP BY
    COALESCE(
        NULLIF(TRIM(format), ''),
        'Unknown'
    )

ORDER BY edition_count DESC;


-- ============================================================
-- 29. ISBN STATUS DISTRIBUTION
-- ============================================================

SELECT
    COALESCE(
        NULLIF(TRIM(isbn_status), ''),
        'Unknown'
    ) AS isbn_status,

    COUNT(*) AS edition_count,

    ROUND(
        100.0 * COUNT(*) /
        (SELECT COUNT(*) FROM book_editions),
        2
    ) AS percentage

FROM book_editions

GROUP BY
    COALESCE(
        NULLIF(TRIM(isbn_status), ''),
        'Unknown'
    )

ORDER BY edition_count DESC;


-- ============================================================
-- 30. DESCRIPTION COVERAGE
-- ============================================================

SELECT
    COUNT(*) AS total_books,

    SUM(
        CASE
            WHEN description IS NOT NULL
             AND TRIM(description) <> ''
            THEN 1
            ELSE 0
        END
    ) AS books_with_description,

    ROUND(
        100.0 *
        SUM(
            CASE
                WHEN description IS NOT NULL
                 AND TRIM(description) <> ''
                THEN 1
                ELSE 0
            END
        ) / COUNT(*),
        2
    ) AS description_coverage_pct

FROM books;


-- Expected approximately:
-- total books = 2067
-- descriptions = 192
-- coverage = 9.29%


-- ============================================================
-- 31. COVER IMAGE COVERAGE
-- ============================================================

SELECT
    COUNT(*) AS total_books,

    SUM(
        CASE
            WHEN cover_url IS NOT NULL
             AND TRIM(cover_url) <> ''
            THEN 1
            ELSE 0
        END
    ) AS books_with_cover,

    ROUND(
        100.0 *
        SUM(
            CASE
                WHEN cover_url IS NOT NULL
                 AND TRIM(cover_url) <> ''
                THEN 1
                ELSE 0
            END
        ) / COUNT(*),
        2
    ) AS cover_coverage_pct

FROM books;


-- Expected approximately:
-- total books = 2067
-- covers = 1888
-- coverage = 91.34%


-- ============================================================
-- 32. AUTHOR COVERAGE
-- ============================================================

SELECT
    COUNT(*) AS total_books,

    SUM(
        CASE
            WHEN author_count > 0
            THEN 1
            ELSE 0
        END
    ) AS books_with_authors,

    SUM(
        CASE
            WHEN author_count = 0
            THEN 1
            ELSE 0
        END
    ) AS books_without_authors,

    ROUND(
        100.0 *
        SUM(
            CASE
                WHEN author_count > 0
                THEN 1
                ELSE 0
            END
        ) / COUNT(*),
        2
    ) AS author_coverage_pct

FROM
(
    SELECT
        b.book_id,

        COUNT(DISTINCT ba.author_id)
            AS author_count

    FROM books AS b

    LEFT JOIN book_authors AS ba
        ON b.book_id = ba.book_id

    GROUP BY b.book_id

) AS author_coverage;


-- Expected approximately:
-- 2059 books with authors
-- 8 books without authors
-- 99.61% coverage


-- ============================================================
-- 33. CATEGORY COVERAGE
-- ============================================================

SELECT
    COUNT(*) AS total_books,

    SUM(
        CASE
            WHEN category_count > 0
            THEN 1
            ELSE 0
        END
    ) AS books_with_categories,

    SUM(
        CASE
            WHEN category_count = 0
            THEN 1
            ELSE 0
        END
    ) AS books_without_categories,

    ROUND(
        100.0 *
        SUM(
            CASE
                WHEN category_count > 0
                THEN 1
                ELSE 0
            END
        ) / COUNT(*),
        2
    ) AS category_coverage_pct

FROM
(
    SELECT
        b.book_id,

        COUNT(DISTINCT bc.category_id)
            AS category_count

    FROM books AS b

    LEFT JOIN book_categories AS bc
        ON b.book_id = bc.book_id

    GROUP BY b.book_id

) AS category_coverage;


-- ============================================================
-- 34. METRIC RECORD COVERAGE
-- ============================================================

SELECT
    COUNT(*) AS total_books,

    SUM(
        CASE
            WHEN metric_count > 0
            THEN 1
            ELSE 0
        END
    ) AS books_with_metric_records,

    SUM(
        CASE
            WHEN metric_count = 0
            THEN 1
            ELSE 0
        END
    ) AS books_without_metric_records,

    ROUND(
        100.0 *
        SUM(
            CASE
                WHEN metric_count > 0
                THEN 1
                ELSE 0
            END
        ) / COUNT(*),
        2
    ) AS metric_record_coverage_pct

FROM
(
    SELECT
        b.book_id,

        COUNT(bm.book_id)
            AS metric_count

    FROM books AS b

    LEFT JOIN book_metrics AS bm
        ON b.book_id = bm.book_id

    GROUP BY b.book_id

) AS metric_coverage;


-- Expected:
-- 2067 total
-- 950 with metric records
-- 1117 without metric records
--
-- Note:
-- Metric-record coverage is different from rating coverage.


-- ============================================================
-- 35. BOOKS WITH DESCRIPTION AND CATEGORY DATA
-- ============================================================

SELECT
    COUNT(DISTINCT b.book_id)
        AS books_with_description_and_categories

FROM books AS b

JOIN book_categories AS bc
    ON b.book_id = bc.book_id

WHERE b.description IS NOT NULL
  AND TRIM(b.description) <> '';


-- ============================================================
-- 36. BOOKS WITH DESCRIPTION BUT NO CATEGORY
-- ============================================================

SELECT
    b.book_id,
    b.title

FROM books AS b

LEFT JOIN book_categories AS bc
    ON b.book_id = bc.book_id

WHERE b.description IS NOT NULL
  AND TRIM(b.description) <> ''

GROUP BY
    b.book_id,
    b.title

HAVING COUNT(bc.category_id) = 0

ORDER BY b.title;


-- ============================================================
-- 37. NLP FEATURE AVAILABILITY
-- ============================================================

SELECT
    COUNT(*) AS total_books,

    SUM(
        CASE
            WHEN title IS NOT NULL
             AND TRIM(title) <> ''
            THEN 1
            ELSE 0
        END
    ) AS title_available,

    SUM(
        CASE
            WHEN description IS NOT NULL
             AND TRIM(description) <> ''
            THEN 1
            ELSE 0
        END
    ) AS description_available,

    (
        SELECT COUNT(DISTINCT book_id)
        FROM book_categories
    ) AS category_available

FROM books;


-- NLP strategy later:
--
-- title
-- + source categories / subjects
-- + description where available
--
-- We will NOT fabricate missing descriptions.


-- ============================================================
-- 38. TITLE KEYWORD ANALYSIS
-- ============================================================
-- Preliminary descriptive analysis only.
-- These are NOT NLP topics or ML clusters.
-- ============================================================

SELECT
    'Leadership' AS theme,
    COUNT(*) AS book_count

FROM books

WHERE LOWER(title) LIKE '%leadership%'

UNION ALL

SELECT
    'Management',
    COUNT(*)

FROM books

WHERE LOWER(title) LIKE '%management%'

UNION ALL

SELECT
    'Emotional Intelligence',
    COUNT(*)

FROM books

WHERE LOWER(title)
      LIKE '%emotional intelligence%'

UNION ALL

SELECT
    'Strategy',
    COUNT(*)

FROM books

WHERE LOWER(title) LIKE '%strategy%'

UNION ALL

SELECT
    'Culture',
    COUNT(*)

FROM books

WHERE LOWER(title) LIKE '%culture%'

UNION ALL

SELECT
    'Team',
    COUNT(*)

FROM books

WHERE LOWER(title) LIKE '%team%'

ORDER BY book_count DESC;


-- ============================================================
-- 39. RECENT BOOKS IN THE DATASET
-- ============================================================

SELECT
    book_id,
    title,
    publication_year_observed,
    source_openlibrary,
    source_leadershipnow

FROM books

WHERE publication_year_observed IS NOT NULL

ORDER BY
    publication_year_observed DESC,
    title

LIMIT 50;


-- ============================================================
-- 40. OPEN LIBRARY EDITION COUNT
-- ============================================================

SELECT
    b.book_id,
    b.title,
    bm.edition_count

FROM books AS b

JOIN book_metrics AS bm
    ON b.book_id = bm.book_id

WHERE bm.edition_count IS NOT NULL

ORDER BY bm.edition_count DESC

LIMIT 25;


-- Edition count may indicate bibliographic reach.
-- It is not a direct measure of book quality.


-- ============================================================
-- 41. HIGH READER-ENGAGEMENT SHORTLIST
-- ============================================================

SELECT
    b.book_id,
    b.title,
    bm.average_rating,
    bm.ratings_count,
    bm.want_to_read_count,
    bm.currently_reading_count,
    bm.already_read_count

FROM books AS b

JOIN book_metrics AS bm
    ON b.book_id = bm.book_id

WHERE bm.ratings_count IS NOT NULL

ORDER BY
    bm.ratings_count DESC,
    bm.want_to_read_count DESC

LIMIT 50;


-- Dataset-derived engagement ranking only.
-- Do not label this objectively as "Top 50 Best Books."


-- ============================================================
-- 42. SOURCE RECORD DISTRIBUTION
-- ============================================================

SELECT
    ds.source_name,
    ds.source_type,
    ds.data_level,

    COUNT(sr.source_record_id)
        AS source_records,

    COUNT(DISTINCT sr.book_id)
        AS distinct_canonical_books

FROM data_sources AS ds

LEFT JOIN source_records AS sr
    ON ds.data_source_id = sr.data_source_id

GROUP BY
    ds.data_source_id,
    ds.source_name,
    ds.source_type,
    ds.data_level

ORDER BY source_records DESC;


-- ============================================================
-- 43. SOURCE RECORD TYPE DISTRIBUTION
-- ============================================================

SELECT
    source_record_type,
    COUNT(*) AS record_count

FROM source_records

GROUP BY source_record_type

ORDER BY record_count DESC;


-- ============================================================
-- 44. MATCH METHOD DISTRIBUTION
-- ============================================================

SELECT
    COALESCE(
        match_method,
        'Not Applicable'
    ) AS match_method,

    COUNT(*) AS record_count

FROM source_records

GROUP BY
    COALESCE(
        match_method,
        'Not Applicable'
    )

ORDER BY record_count DESC;


-- ============================================================
-- 45. MATCH CONFIDENCE DISTRIBUTION
-- ============================================================
-- match_confidence is categorical metadata in the final schema.
-- ============================================================

SELECT
    COALESCE(
        match_confidence,
        'Not Applicable'
    ) AS match_confidence,

    COUNT(*) AS record_count

FROM source_records

GROUP BY
    COALESCE(
        match_confidence,
        'Not Applicable'
    )

ORDER BY record_count DESC;


-- ============================================================
-- 46. FINAL ANALYTICAL COVERAGE SUMMARY
-- ============================================================

SELECT
    (SELECT COUNT(*) FROM books)
        AS total_books,

    (SELECT COUNT(DISTINCT book_id)
     FROM book_authors)
        AS books_with_authors,

    (SELECT COUNT(DISTINCT book_id)
     FROM book_categories)
        AS books_with_categories,

    (
        SELECT COUNT(*)
        FROM books
        WHERE description IS NOT NULL
          AND TRIM(description) <> ''
    ) AS books_with_description,

    (
        SELECT COUNT(*)
        FROM books
        WHERE cover_url IS NOT NULL
          AND TRIM(cover_url) <> ''
    ) AS books_with_cover,

    (SELECT COUNT(*) FROM book_metrics)
        AS books_with_metric_records;


-- Expected approximately:
--
-- total_books               = 2067
-- books_with_authors        = 2059
-- books_with_description    = 192
-- books_with_cover          = 1888
-- books_with_metric_records = 950


-- ============================================================
-- 47. FINAL PROJECT DATABASE SUMMARY
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
    ) AS confirmed_cross_source_books;


-- Expected:
--
-- books                        = 2067
-- authors                      = 2281
-- categories                   = 2187
-- editions                     = 1120
-- metric_records               = 950
-- source_records               = 2070
-- confirmed_cross_source_books = 3


-- ============================================================
-- END OF 05_analysis_queries.sql
-- ============================================================