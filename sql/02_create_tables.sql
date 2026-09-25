-- =====================================================
-- LEADERSHIP & MANAGEMENT BOOK RECOMMENDATION SYSTEM
-- 02_create_tables.sql
-- =====================================================

USE leadership_books_db;

-- =====================================================
-- CLEAN EXISTING / PARTIAL TABLES
-- =====================================================

SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS source_records;
DROP TABLE IF EXISTS book_metrics;
DROP TABLE IF EXISTS book_editions;
DROP TABLE IF EXISTS book_categories;
DROP TABLE IF EXISTS book_authors;
DROP TABLE IF EXISTS data_sources;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS authors;
DROP TABLE IF EXISTS books;

SET FOREIGN_KEY_CHECKS = 1;


-- =====================================================
-- 1. BOOKS
-- Master record: one row per canonical book
-- =====================================================

CREATE TABLE books (
    book_id VARCHAR(20) PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    first_publish_year INT,
    publication_year_observed INT,
    cover_url TEXT,
    openlibrary_key VARCHAR(50),
    source_openlibrary BOOLEAN NOT NULL DEFAULT FALSE,
    source_leadershipnow BOOLEAN NOT NULL DEFAULT FALSE
);


-- =====================================================
-- 2. AUTHORS
-- Unique normalized author records
-- =====================================================

CREATE TABLE authors (
    author_id VARCHAR(20) PRIMARY KEY,
    author_name VARCHAR(300) NOT NULL,
    author_normalized VARCHAR(300) NOT NULL UNIQUE
);


-- =====================================================
-- 3. BOOK_AUTHORS
-- Many-to-many relationship between books and authors
-- =====================================================

CREATE TABLE book_authors (
    book_id VARCHAR(20) NOT NULL,
    author_id VARCHAR(20) NOT NULL,

    PRIMARY KEY (book_id, author_id),

    CONSTRAINT fk_book_authors_book
        FOREIGN KEY (book_id)
        REFERENCES books(book_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_book_authors_author
        FOREIGN KEY (author_id)
        REFERENCES authors(author_id)
        ON DELETE CASCADE
);


-- =====================================================
-- 4. CATEGORIES
-- Unique normalized subject/category records
-- =====================================================

CREATE TABLE categories (
    category_id VARCHAR(20) PRIMARY KEY,
    category_name VARCHAR(500) NOT NULL,
    category_normalized VARCHAR(500) NOT NULL UNIQUE
);


-- =====================================================
-- 5. BOOK_CATEGORIES
-- Many-to-many relationship between books and categories
-- =====================================================

CREATE TABLE book_categories (
    book_id VARCHAR(20) NOT NULL,
    category_id VARCHAR(20) NOT NULL,

    PRIMARY KEY (book_id, category_id),

    CONSTRAINT fk_book_categories_book
        FOREIGN KEY (book_id)
        REFERENCES books(book_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_book_categories_category
        FOREIGN KEY (category_id)
        REFERENCES categories(category_id)
        ON DELETE CASCADE
);


-- =====================================================
-- 6. BOOK_EDITIONS
-- LeadershipNow edition-level metadata
-- =====================================================

CREATE TABLE book_editions (
    edition_id VARCHAR(20) PRIMARY KEY,
    book_id VARCHAR(20) NOT NULL,

    scrape_id INT NOT NULL,
    isbn_source VARCHAR(50),
    isbn_normalized VARCHAR(20),
    isbn_13 VARCHAR(20),
    isbn_status VARCHAR(50),

    publisher VARCHAR(300),
    publication_date DATE,
    publication_year INT,

    format VARCHAR(100),
    page_count INT,
    edition_note VARCHAR(500),

    cover_url TEXT,
    external_book_url TEXT,

    source_metadata_conflict BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT uq_book_editions_scrape_id
        UNIQUE (scrape_id),

    CONSTRAINT fk_book_editions_book
        FOREIGN KEY (book_id)
        REFERENCES books(book_id)
        ON DELETE CASCADE
);


-- =====================================================
-- 7. BOOK_METRICS
-- Open Library rating / engagement metrics
-- One metric record per book
-- =====================================================

CREATE TABLE book_metrics (
    book_id VARCHAR(20) PRIMARY KEY,

    average_rating DECIMAL(5,2),
    ratings_count BIGINT,
    edition_count INT,
    want_to_read_count BIGINT,
    currently_reading_count BIGINT,
    already_read_count BIGINT,

    CONSTRAINT fk_book_metrics_book
        FOREIGN KEY (book_id)
        REFERENCES books(book_id)
        ON DELETE CASCADE
);


-- =====================================================
-- 8. DATA_SOURCES
-- Source reference table
-- =====================================================

CREATE TABLE data_sources (
    data_source_id VARCHAR(20) PRIMARY KEY,
    source_name VARCHAR(100) NOT NULL UNIQUE,
    source_type VARCHAR(100) NOT NULL,
    data_level VARCHAR(100) NOT NULL
);


-- =====================================================
-- 9. SOURCE_RECORDS
-- Traceability between canonical books and source records
-- =====================================================

CREATE TABLE source_records (
    source_record_id VARCHAR(30) PRIMARY KEY,
    book_id VARCHAR(20) NOT NULL,
    data_source_id VARCHAR(20) NOT NULL,

    source_native_id VARCHAR(100),
    source_record_type VARCHAR(100) NOT NULL,
    source_url TEXT,

    query_match_count INT,
    release_pages TEXT,

    match_method VARCHAR(100),
    match_confidence VARCHAR(50),

    CONSTRAINT fk_source_records_book
        FOREIGN KEY (book_id)
        REFERENCES books(book_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_source_records_source
        FOREIGN KEY (data_source_id)
        REFERENCES data_sources(data_source_id)
        ON DELETE CASCADE
);


-- =====================================================
-- INDEXES
-- =====================================================

CREATE INDEX idx_books_openlibrary_key
    ON books(openlibrary_key);

CREATE INDEX idx_books_first_publish_year
    ON books(first_publish_year);

CREATE INDEX idx_books_publication_year
    ON books(publication_year_observed);

CREATE INDEX idx_editions_isbn13
    ON book_editions(isbn_13);

CREATE INDEX idx_editions_publication_year
    ON book_editions(publication_year);

CREATE INDEX idx_editions_publisher
    ON book_editions(publisher);

CREATE INDEX idx_metrics_ratings_count
    ON book_metrics(ratings_count);

CREATE INDEX idx_source_records_book
    ON source_records(book_id);

CREATE INDEX idx_source_records_source
    ON source_records(data_source_id);


-- =====================================================
-- VERIFY TABLE CREATION
-- =====================================================

SHOW TABLES;
USE leadership_books_db;

SHOW INDEX FROM categories;
ALTER TABLE categories
DROP INDEX category_normalized;
USE leadership_books_db;

SELECT 'books' AS table_name, COUNT(*) AS row_count FROM books
UNION ALL
SELECT 'authors', COUNT(*) FROM authors
UNION ALL
SELECT 'categories', COUNT(*) FROM categories
UNION ALL
SELECT 'data_sources', COUNT(*) FROM data_sources
UNION ALL
SELECT 'book_authors', COUNT(*) FROM book_authors
UNION ALL
SELECT 'book_categories', COUNT(*) FROM book_categories
UNION ALL
SELECT 'book_editions', COUNT(*) FROM book_editions
UNION ALL
SELECT 'book_metrics', COUNT(*) FROM book_metrics
UNION ALL
SELECT 'source_records', COUNT(*) FROM source_records;
SHOW CREATE TABLE categories;
