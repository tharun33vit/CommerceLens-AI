/* ==============================================================================
   CommerceLens AI — Power Query (M) Ingestion & Transformation Scripts
   Target Database: PostgreSQL (localhost:5432 / commercelens_db)
   Connectivity Mode: Import
   Authentication: Database Credentials (Configured via Power BI Data Source Settings)
   ============================================================================== */

// ==============================================================================
// 1. DIMENSION TABLES
// ==============================================================================

// Table: DimDate
let
    Source = PostgreSQL.Database("localhost:5432", "commercelens_db", [
        Query = "SELECT date_key, full_date, year, quarter, month, month_year, day_of_week, is_weekend FROM dim_date ORDER BY date_key;"
    ]),
    #"Changed Type" = Table.TransformColumnTypes(Source, {
        {"date_key", Int64.Type},
        {"full_date", type date},
        {"year", Int64.Type},
        {"quarter", Int64.Type},
        {"month", Int64.Type},
        {"month_year", type text},
        {"day_of_week", Int64.Type},
        {"is_weekend", type logical}
    })
in
    #"Changed Type"

// Table: DimCustomers
let
    Source = PostgreSQL.Database("localhost:5432", "commercelens_db", [
        Query = "SELECT customer_key, customer_id, customer_unique_id, zip_code_prefix, city, state FROM dim_customers;"
    ]),
    #"Changed Type" = Table.TransformColumnTypes(Source, {
        {"customer_key", Int64.Type},
        {"customer_id", type text},
        {"customer_unique_id", type text},
        {"zip_code_prefix", type text},
        {"city", type text},
        {"state", type text}
    })
in
    #"Changed Type"

// Table: DimSellers
let
    Source = PostgreSQL.Database("localhost:5432", "commercelens_db", [
        Query = "SELECT seller_key, seller_id, zip_code_prefix, city, state FROM dim_sellers;"
    ]),
    #"Changed Type" = Table.TransformColumnTypes(Source, {
        {"seller_key", Int64.Type},
        {"seller_id", type text},
        {"zip_code_prefix", type text},
        {"city", type text},
        {"state", type text}
    })
in
    #"Changed Type"

// Table: DimProducts
let
    Source = PostgreSQL.Database("localhost:5432", "commercelens_db", [
        Query = "SELECT product_key, product_id, category_name_portuguese, category_name_english, product_weight_g, product_photos_qty FROM dim_products;"
    ]),
    #"Changed Type" = Table.TransformColumnTypes(Source, {
        {"product_key", Int64.Type},
        {"product_id", type text},
        {"category_name_portuguese", type text},
        {"category_name_english", type text},
        {"product_weight_g", Int64.Type},
        {"product_photos_qty", Int64.Type}
    })
in
    #"Changed Type"

// Table: DimGeography
let
    Source = PostgreSQL.Database("localhost:5432", "commercelens_db", [
        Query = "SELECT geo_key, zip_code_prefix, latitude, longitude, state, city, sample_points_count FROM dim_geography;"
    ]),
    #"Changed Type" = Table.TransformColumnTypes(Source, {
        {"geo_key", Int64.Type},
        {"zip_code_prefix", type text},
        {"latitude", type number},
        {"longitude", type number},
        {"state", type text},
        {"city", type text},
        {"sample_points_count", Int64.Type}
    })
in
    #"Changed Type"


// ==============================================================================
// 2. FACT TABLES
// ==============================================================================

// Table: FactOrders (Order Grain - 99,441 rows)
let
    Source = PostgreSQL.Database("localhost:5432", "commercelens_db", [
        Query = "SELECT order_id, customer_key, purchase_date_key, order_status, order_purchase_timestamp, order_delivered_customer_date, order_estimated_delivery_date, is_delivered, is_late, is_eligible_for_sla, delivery_lead_time_days, carrier_transit_days, seller_dispatch_days, sla_variance_days, total_items_count, total_item_merchandise_value, total_freight_value, total_order_gross_value, total_payment_value, payment_slices_count FROM fact_orders;"
    ]),
    #"Changed Type" = Table.TransformColumnTypes(Source, {
        {"order_id", type text},
        {"customer_key", Int64.Type},
        {"purchase_date_key", Int64.Type},
        {"order_status", type text},
        {"order_purchase_timestamp", type datetime},
        {"order_delivered_customer_date", type datetime},
        {"order_estimated_delivery_date", type datetime},
        {"is_delivered", type logical},
        {"is_late", type logical},
        {"is_eligible_for_sla", type logical},
        {"delivery_lead_time_days", type number},
        {"carrier_transit_days", type number},
        {"seller_dispatch_days", type number},
        {"sla_variance_days", type number},
        {"total_items_count", Int64.Type},
        {"total_item_merchandise_value", Currency.Type},
        {"total_freight_value", Currency.Type},
        {"total_order_gross_value", Currency.Type},
        {"total_payment_value", Currency.Type},
        {"payment_slices_count", Int64.Type}
    })
in
    #"Changed Type"

// Table: FactOrderItems (Item Line Grain - 112,650 rows)
let
    Source = PostgreSQL.Database("localhost:5432", "commercelens_db", [
        Query = "SELECT order_item_key, order_id, order_item_id, product_key, seller_key, shipping_limit_date, price, freight_value, total_item_value FROM fact_order_items;"
    ]),
    #"Changed Type" = Table.TransformColumnTypes(Source, {
        {"order_item_key", Int64.Type},
        {"order_id", type text},
        {"order_item_id", Int64.Type},
        {"product_key", Int64.Type},
        {"seller_key", Int64.Type},
        {"shipping_limit_date", type datetime},
        {"price", Currency.Type},
        {"freight_value", Currency.Type},
        {"total_item_value", Currency.Type}
    })
in
    #"Changed Type"

// Table: FactPayments (Payment Slice Grain - 103,886 rows)
let
    Source = PostgreSQL.Database("localhost:5432", "commercelens_db", [
        Query = "SELECT payment_key, order_id, payment_sequential, payment_type, payment_installments, payment_value FROM fact_payments;"
    ]),
    #"Changed Type" = Table.TransformColumnTypes(Source, {
        {"payment_key", Int64.Type},
        {"order_id", type text},
        {"payment_sequential", Int64.Type},
        {"payment_type", type text},
        {"payment_installments", Int64.Type},
        {"payment_value", Currency.Type}
    })
in
    #"Changed Type"

// Table: FactReviews (Compound Review Grain - 99,224 rows)
let
    Source = PostgreSQL.Database("localhost:5432", "commercelens_db", [
        Query = "SELECT review_key, review_id, order_id, review_score, review_comment_title, review_comment_message, review_creation_date, review_answer_timestamp FROM fact_reviews;"
    ]),
    #"Changed Type" = Table.TransformColumnTypes(Source, {
        {"review_key", Int64.Type},
        {"review_id", type text},
        {"order_id", type text},
        {"review_score", Int64.Type},
        {"review_comment_title", type text},
        {"review_comment_message", type text},
        {"review_creation_date", type datetime},
        {"review_answer_timestamp", type datetime}
    })
in
    #"Changed Type"


// ==============================================================================
// 3. SEMANTIC VIEW
// ==============================================================================

// Table: VDeliverySLAOperations
let
    Source = PostgreSQL.Database("localhost:5432", "commercelens_db", [
        Query = "SELECT total_orders, delivered_orders_total, sla_eligible_delivered_orders, delivered_missing_timestamp_orders, on_time_orders_count, late_orders_count, on_time_delivery_rate_pct, late_delivery_rate_pct, avg_delivery_lead_time_days, avg_carrier_transit_days, avg_seller_dispatch_days, avg_sla_variance_buffer_days FROM v_delivery_sla_operations;"
    ]),
    #"Changed Type" = Table.TransformColumnTypes(Source, {
        {"total_orders", Int64.Type},
        {"delivered_orders_total", Int64.Type},
        {"sla_eligible_delivered_orders", Int64.Type},
        {"delivered_missing_timestamp_orders", Int64.Type},
        {"on_time_orders_count", Int64.Type},
        {"late_orders_count", Int64.Type},
        {"on_time_delivery_rate_pct", type number},
        {"late_delivery_rate_pct", type number},
        {"avg_delivery_lead_time_days", type number},
        {"avg_carrier_transit_days", type number},
        {"avg_seller_dispatch_days", type number},
        {"avg_sla_variance_buffer_days", type number}
    })
in
    #"Changed Type"
