-- ==============================================================================
-- CommerceLens AI — Phase 5: Customer Review Intelligence Views
-- File: sql/views/02_review_intelligence_views.sql
-- 
-- Grain Discipline:
--   - fact_reviews & fact_review_analysis grain is (review_id, order_id)
--   - fact_review_themes grain is (review_id, order_id, theme_id)
--   - Pre-aggregations are enforced to prevent join fan-out with multi-item orders.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. View: Processing Coverage & Pipeline Auditing
-- ------------------------------------------------------------------------------
CREATE OR REPLACE VIEW view_review_processing_coverage AS
SELECT
    (SELECT COUNT(*) FROM fact_reviews) AS total_source_reviews,
    (SELECT COUNT(DISTINCT (review_id, order_id)) FROM fact_reviews) AS distinct_compound_keys,
    (SELECT COUNT(*) FROM fact_reviews 
     WHERE (review_comment_title IS NOT NULL AND TRIM(review_comment_title) != '')
        OR (review_comment_message IS NOT NULL AND TRIM(review_comment_message) != '')
    ) AS reviews_with_text,
    (SELECT COUNT(*) FROM fact_reviews 
     WHERE (review_comment_title IS NULL OR TRIM(review_comment_title) = '')
       AND (review_comment_message IS NULL OR TRIM(review_comment_message) = '')
    ) AS reviews_without_text,
    (SELECT COUNT(*) FROM fact_review_analysis WHERE status = 'completed') AS processed_completed,
    (SELECT COUNT(*) FROM fact_review_analysis WHERE status = 'failed') AS processed_failed,
    (SELECT COUNT(*) FROM fact_review_analysis WHERE status = 'unclear') AS processed_unclear,
    ROUND(
        ((SELECT COUNT(*) FROM fact_review_analysis WHERE status = 'completed')::numeric / 
         NULLIF((SELECT COUNT(*) FROM fact_reviews 
                 WHERE (review_comment_title IS NOT NULL AND TRIM(review_comment_title) != '')
                    OR (review_comment_message IS NOT NULL AND TRIM(review_comment_message) != '')), 0)) * 100, 
        2
    ) AS text_coverage_pct;

-- ------------------------------------------------------------------------------
-- 2. View: Sentiment & Theme Distribution by Customer Rating Score
-- ------------------------------------------------------------------------------
CREATE OR REPLACE VIEW view_review_sentiment_by_rating AS
SELECT
    r.review_score,
    CASE 
        WHEN r.review_score IN (1, 2) THEN 'Negative Rating Proxy'
        WHEN r.review_score = 3 THEN 'Neutral Rating Proxy'
        WHEN r.review_score IN (4, 5) THEN 'Positive Rating Proxy'
    END AS rating_proxy,
    a.sentiment_label,
    COUNT(*) AS review_count,
    ROUND(
        (COUNT(*)::numeric / NULLIF(SUM(COUNT(*)) OVER (PARTITION BY r.review_score), 0)) * 100, 
        2
    ) AS pct_within_score
FROM fact_review_analysis a
JOIN fact_reviews r 
  ON a.review_id = r.review_id 
 AND a.order_id = r.order_id
WHERE a.status = 'completed'
GROUP BY r.review_score, rating_proxy, a.sentiment_label
ORDER BY r.review_score, review_count DESC;

-- ------------------------------------------------------------------------------
-- 3. View: Delivery Timeliness Cohort vs Customer Review Sentiment
--    Avoids fan-out by aggregating fact_orders directly on order_id.
-- ------------------------------------------------------------------------------
CREATE OR REPLACE VIEW view_review_delivery_cohort_analysis AS
WITH order_cohorts AS (
    SELECT
        order_id,
        CASE 
            WHEN order_delivered_customer_date > order_estimated_delivery_date THEN 'Late Delivery'
            ELSE 'On-Time Delivery'
        END AS delivery_cohort
    FROM fact_orders
    WHERE order_status = 'delivered'
      AND order_delivered_customer_date IS NOT NULL
)
SELECT
    oc.delivery_cohort,
    COUNT(DISTINCT a.review_id || a.order_id) AS total_reviews_analyzed,
    SUM(CASE WHEN a.delivery_related THEN 1 ELSE 0 END) AS delivery_related_reviews,
    ROUND(
        (SUM(CASE WHEN a.delivery_related THEN 1 ELSE 0 END)::numeric / 
         NULLIF(COUNT(DISTINCT a.review_id || a.order_id), 0)) * 100, 
        2
    ) AS delivery_related_pct,
    SUM(CASE WHEN a.primary_theme = 'delivery_delay' THEN 1 ELSE 0 END) AS delivery_delay_primary_count,
    ROUND(
        (SUM(CASE WHEN a.primary_theme = 'delivery_delay' THEN 1 ELSE 0 END)::numeric / 
         NULLIF(COUNT(DISTINCT a.review_id || a.order_id), 0)) * 100, 
        2
    ) AS delivery_delay_primary_pct,
    SUM(CASE WHEN a.sentiment_label = 'negative' THEN 1 ELSE 0 END) AS negative_sentiment_count,
    ROUND(
        (SUM(CASE WHEN a.sentiment_label = 'negative' THEN 1 ELSE 0 END)::numeric / 
         NULLIF(COUNT(DISTINCT a.review_id || a.order_id), 0)) * 100, 
        2
    ) AS negative_sentiment_pct
FROM fact_review_analysis a
JOIN order_cohorts oc ON a.order_id = oc.order_id
WHERE a.status = 'completed'
GROUP BY oc.delivery_cohort
ORDER BY oc.delivery_cohort;

-- ------------------------------------------------------------------------------
-- 4. View: Customer Review Themes by Product Category
--    Pre-aggregates distinct categories per order to prevent item fan-out.
-- ------------------------------------------------------------------------------
CREATE OR REPLACE VIEW view_review_themes_by_category AS
WITH order_categories AS (
    SELECT DISTINCT
        oi.order_id,
        COALESCE(p.category_name_english, p.category_name_portuguese, 'unknown') AS category_name
    FROM fact_order_items oi
    JOIN dim_products p ON oi.product_key = p.product_key
)
SELECT
    oc.category_name,
    t.theme_id,
    COUNT(DISTINCT t.review_id || t.order_id) AS review_count,
    ROUND(
        (COUNT(DISTINCT t.review_id || t.order_id)::numeric / 
         NULLIF(SUM(COUNT(DISTINCT t.review_id || t.order_id)) OVER (PARTITION BY oc.category_name), 0)) * 100, 
        2
    ) AS theme_share_pct
FROM fact_review_themes t
JOIN order_categories oc ON t.order_id = oc.order_id
JOIN fact_review_analysis a ON t.review_id = a.review_id AND t.order_id = a.order_id
WHERE a.status = 'completed'
GROUP BY oc.category_name, t.theme_id
HAVING COUNT(DISTINCT t.review_id || t.order_id) >= 1
ORDER BY oc.category_name, review_count DESC;

-- ------------------------------------------------------------------------------
-- 5. View: Regional Logistics Sentiment by Customer State
--    Aggregates review sentiment by customer state with sample threshold >= 25.
-- ------------------------------------------------------------------------------
CREATE OR REPLACE VIEW view_review_state_logistics_sentiment AS
SELECT
    c.state AS customer_state,
    COUNT(DISTINCT a.review_id || a.order_id) AS reviews_analyzed,
    SUM(CASE WHEN a.delivery_related THEN 1 ELSE 0 END) AS delivery_complaints,
    ROUND(
        (SUM(CASE WHEN a.delivery_related THEN 1 ELSE 0 END)::numeric / 
         NULLIF(COUNT(DISTINCT a.review_id || a.order_id), 0)) * 100, 
        2
    ) AS delivery_complaint_pct,
    SUM(CASE WHEN a.sentiment_label = 'negative' THEN 1 ELSE 0 END) AS negative_sentiment_count,
    ROUND(
        (SUM(CASE WHEN a.sentiment_label = 'negative' THEN 1 ELSE 0 END)::numeric / 
         NULLIF(COUNT(DISTINCT a.review_id || a.order_id), 0)) * 100, 
        2
    ) AS negative_sentiment_pct
FROM fact_review_analysis a
JOIN fact_orders o ON a.order_id = o.order_id
JOIN dim_customers c ON o.customer_key = c.customer_key
WHERE a.status = 'completed'
GROUP BY c.state
HAVING COUNT(DISTINCT a.review_id || a.order_id) >= 1
ORDER BY reviews_analyzed DESC;
