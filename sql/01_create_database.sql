-- =====================================================
-- LEADERSHIP & MANAGEMENT BOOK RECOMMENDATION SYSTEM
-- 01_create_database.sql
-- =====================================================

-- Create the database only if it does not already exist
CREATE DATABASE IF NOT EXISTS leadership_books_db
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

-- Select the database
USE leadership_books_db;

-- Verify active database
SELECT DATABASE() AS active_database;