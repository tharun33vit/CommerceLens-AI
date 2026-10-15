"""
Power BI DAX Measures Verification & Database Reconciliation Script.

Validates that mathematical definitions of all Power BI measures
reconcile exactly with live PostgreSQL query outputs from commercelens_db.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from commercelens.analytics.db import create_db_engine, mask_connection_url
from sqlalchemy import text
import pandas as pd


def verify_all_measures():
    engine = create_db_engine()
    print(f"Connecting to database: {mask_connection_url(str(engine.url))}")

    results = []

    with engine.connect() as conn:
        # 1. Distinct Orders
        total_orders = conn.execute(text("SELECT COUNT(DISTINCT order_id) FROM fact_orders;")).scalar()
        results.append(("Total Orders", "Distinct count of all orders in marketplace", total_orders, "orders", "COUNT(DISTINCT order_id)"))

        # 2. Delivered Orders
        delivered_orders = conn.execute(text("SELECT COUNT(DISTINCT order_id) FROM fact_orders WHERE order_status = 'delivered';")).scalar()
        results.append(("Delivered Orders", "Distinct delivered orders", delivered_orders, "orders", "order_status = 'delivered'"))

        # 3. SLA-Eligible Orders (Strict Denominator)
        sla_eligible = conn.execute(text("SELECT COUNT(DISTINCT order_id) FROM fact_orders WHERE is_eligible_for_sla = TRUE;")).scalar()
        results.append(("SLA-Eligible Orders", "Delivered orders with non-null customer delivery date", sla_eligible, "orders", "is_eligible_for_sla = TRUE (96,478 - 8 = 96,470)"))

        # 4. Delivered Missing Timestamp Orders
        missing_ts = conn.execute(text("SELECT COUNT(DISTINCT order_id) FROM fact_orders WHERE order_status = 'delivered' AND order_delivered_customer_date IS NULL;")).scalar()
        results.append(("Delivered Missing Timestamp Orders", "Delivered orders missing actual delivery timestamp", missing_ts, "orders", "Audited operational exception (8 orders)"))

        # 5. On-Time Orders
        on_time = conn.execute(text("SELECT COUNT(DISTINCT order_id) FROM fact_orders WHERE is_eligible_for_sla = TRUE AND is_late = FALSE;")).scalar()
        results.append(("On-Time Orders", "SLA-eligible orders delivered on or before estimated date", on_time, "orders", "is_eligible_for_sla = TRUE AND is_late = FALSE"))

        # 6. Late Orders
        late = conn.execute(text("SELECT COUNT(DISTINCT order_id) FROM fact_orders WHERE is_eligible_for_sla = TRUE AND is_late = TRUE;")).scalar()
        results.append(("Late Orders", "SLA-eligible orders delivered after estimated date", late, "orders", "is_eligible_for_sla = TRUE AND is_late = TRUE"))

        # 7. On-Time Delivery Rate (OTDR)
        otdr = round((on_time / sla_eligible) * 100, 2)
        results.append(("On-Time Delivery Rate (OTDR)", "On-Time Orders / SLA-Eligible Orders", f"{otdr}%", "rate", "88,644 / 96,470 = 91.89%"))

        # 8. Late Delivery Rate (LDR)
        ldr = round((late / sla_eligible) * 100, 2)
        results.append(("Late Delivery Rate (LDR)", "Late Orders / SLA-Eligible Orders", f"{ldr}%", "rate", "7,826 / 96,470 = 8.11%"))

        # 9. Canceled Orders & Rate
        canceled = conn.execute(text("SELECT COUNT(DISTINCT order_id) FROM fact_orders WHERE order_status = 'canceled';")).scalar()
        canc_rate = round((canceled / total_orders) * 100, 4)
        results.append(("Canceled Orders", "Orders with canceled status", canceled, "orders", f"{canceled:,} orders"))
        results.append(("Cancellation Rate", "Canceled Orders / Total Orders Placed", f"{canc_rate}%", "rate", "625 / 99,441 = 0.6285%"))

        # 10. Unavailable Orders & Rate
        unavail = conn.execute(text("SELECT COUNT(DISTINCT order_id) FROM fact_orders WHERE order_status = 'unavailable';")).scalar()
        unavail_rate = round((unavail / total_orders) * 100, 4)
        results.append(("Unavailable Orders", "Orders with unavailable status (stockouts)", unavail, "orders", f"{unavail:,} orders"))
        results.append(("Unavailable Order Rate", "Unavailable Orders / Total Orders Placed", f"{unavail_rate}%", "rate", "609 / 99,441 = 0.6124%"))

        # 11. GMV Delivered
        gmv_deliv = conn.execute(text("SELECT SUM(foi.price) FROM fact_order_items foi JOIN fact_orders fo ON foi.order_id = fo.order_id WHERE fo.order_status = 'delivered';")).scalar()
        results.append(("Total GMV (Delivered)", "Item merchandise value of delivered orders", f"R$ {float(gmv_deliv):,.2f}", "currency", "SUM(FactOrderItems[price]) for delivered orders"))

        # 12. Total Item Price (All transacted items)
        gmv_all = conn.execute(text("SELECT SUM(price) FROM fact_order_items;")).scalar()
        results.append(("Total Merchandise Value (All Items)", "Gross item merchandise price across all orders", f"R$ {float(gmv_all):,.2f}", "currency", "SUM(FactOrderItems[price])"))

        # 13. Total Freight Spend (Delivered)
        freight_deliv = conn.execute(text("SELECT SUM(foi.freight_value) FROM fact_order_items foi JOIN fact_orders fo ON foi.order_id = fo.order_id WHERE fo.order_status = 'delivered';")).scalar()
        results.append(("Total Freight (Delivered)", "Shipping fees collected on delivered orders", f"R$ {float(freight_deliv):,.2f}", "currency", "SUM(FactOrderItems[freight_value]) for delivered orders"))

        # 14. Average Order Value (AOV)
        aov = round(float(gmv_deliv) / delivered_orders, 2)
        results.append(("Average Order Value (AOV)", "Total Delivered GMV / Delivered Orders Count", f"R$ {aov:,.2f}", "currency", "R$ 13,221,498.11 / 96,478 = R$ 137.04"))

        # 15. Freight-to-Merchandise Ratio
        freight_ratio = round((float(freight_deliv) / float(gmv_deliv)) * 100, 2)
        results.append(("Freight-to-Merchandise Ratio", "Total Freight / Total GMV", f"{freight_ratio}%", "rate", "R$ 2,198,275.64 / R$ 13,221,498.11 = 16.63%"))

        # 16. Total Payments Collected
        total_payments = conn.execute(text("SELECT SUM(payment_value) FROM fact_payments;")).scalar()
        results.append(("Total Payments Value", "Gross payment volume collected from all slices", f"R$ {float(total_payments):,.2f}", "currency", "SUM(FactPayments[payment_value])"))

        # 17. Logistics Durations
        lead_time = conn.execute(text("SELECT ROUND(AVG(delivery_lead_time_days), 2) FROM fact_orders WHERE is_eligible_for_sla = TRUE;")).scalar()
        transit_time = conn.execute(text("SELECT ROUND(AVG(carrier_transit_days), 2) FROM fact_orders WHERE is_eligible_for_sla = TRUE;")).scalar()
        seller_lead = conn.execute(text("SELECT ROUND(AVG(seller_dispatch_days), 2) FROM fact_orders WHERE is_eligible_for_sla = TRUE;")).scalar()
        results.append(("Avg Delivery Lead Time", "Purchase to customer delivery duration", f"{lead_time} days", "duration", "AVG(delivery_lead_time_days) for SLA eligible"))
        results.append(("Avg Carrier Transit Duration", "Carrier pickup to customer delivery duration", f"{transit_time} days", "duration", "AVG(carrier_transit_days) for SLA eligible"))
        results.append(("Avg Seller Dispatch Duration", "Order approval to carrier pickup duration", f"{seller_lead} days", "duration", "AVG(seller_dispatch_days) for SLA eligible"))

        # 18. Customer CSAT & Review Scores
        avg_csat = conn.execute(text("SELECT ROUND(AVG(review_score), 2) FROM fact_reviews;")).scalar()
        on_time_csat = conn.execute(text("SELECT ROUND(AVG(fr.review_score), 2) FROM fact_reviews fr JOIN fact_orders fo ON fr.order_id = fo.order_id WHERE fo.is_eligible_for_sla = TRUE AND fo.is_late = FALSE;")).scalar()
        late_csat = conn.execute(text("SELECT ROUND(AVG(fr.review_score), 2) FROM fact_reviews fr JOIN fact_orders fo ON fr.order_id = fo.order_id WHERE fo.is_eligible_for_sla = TRUE AND fo.is_late = TRUE;")).scalar()
        
        on_time_raw = conn.execute(text("SELECT AVG(fr.review_score) FROM fact_reviews fr JOIN fact_orders fo ON fr.order_id = fo.order_id WHERE fo.is_eligible_for_sla = TRUE AND fo.is_late = FALSE;")).scalar()
        late_raw = conn.execute(text("SELECT AVG(fr.review_score) FROM fact_reviews fr JOIN fact_orders fo ON fr.order_id = fo.order_id WHERE fo.is_eligible_for_sla = TRUE AND fo.is_late = TRUE;")).scalar()

        # Consistent formula and sign alignment from unrounded averages:
        # CSAT Delivery Penalty = [Late Order CSAT] - [On-Time Order CSAT] = 2.566493 - 4.293718 = -1.72722... -> -1.73 stars
        # CSAT Timeliness Gap   = [On-Time Order CSAT] - [Late Order CSAT] = 4.293718 - 2.566493 = +1.72722... -> +1.73 stars
        csat_penalty = round(float(late_raw) - float(on_time_raw), 2)
        csat_gap = round(float(on_time_raw) - float(late_raw), 2)
        
        results.append(("Average Review Score (CSAT)", "Overall average customer satisfaction score (1-5)", avg_csat, "score", "AVG(review_score) across all 99,224 reviews"))
        results.append(("On-Time Orders CSAT", "Average rating for orders arriving on schedule", on_time_csat, "score", "4.29 stars (N = 88,653 reviews across 88,163 orders)"))
        results.append(("Late Orders CSAT", "Average rating for orders breaching delivery SLA", late_csat, "score", "2.57 stars (N = 7,700 reviews across 7,661 orders)"))
        results.append(("CSAT Delivery Penalty", "Score drop associated with late fulfillment [Late] - [On-Time]", f"{csat_penalty:.2f} stars", "score", "2.566 - 4.294 = -1.73 stars penalty"))
        results.append(("CSAT Timeliness Gap", "Satisfaction premium for on-time fulfillment [On-Time] - [Late]", f"+{csat_gap:.2f} stars", "score", "4.294 - 2.566 = +1.73 stars gap"))

        # 19. Customer Retention & Repeat Buyers
        cust_stats = conn.execute(text("""
            WITH user_orders AS (
                SELECT dc.customer_unique_id, COUNT(fo.order_id) AS orders
                FROM dim_customers dc
                JOIN fact_orders fo ON dc.customer_key = fo.customer_key
                GROUP BY dc.customer_unique_id
            )
            SELECT 
                COUNT(*) AS total_unique_users,
                COUNT(CASE WHEN orders > 1 THEN 1 END) AS repeat_users
            FROM user_orders;
        """)).mappings().first()
        unique_users = cust_stats['total_unique_users']
        repeat_users = cust_stats['repeat_users']
        repeat_rate = round((repeat_users / unique_users) * 100, 4)
        results.append(("Unique Human Customers", "Persistent consumer count (customer_unique_id)", f"{unique_users:,}", "count", "DISTINCTCOUNT(DimCustomers[customer_unique_id])"))
        results.append(("Repeat Customers Count", "Consumers placing 2 or more orders", f"{repeat_users:,}", "count", "2,997 repeat buyers"))
        results.append(("Repeat Customer Rate", "Repeat Buyers / Total Unique Customers", f"{repeat_rate}%", "rate", "2,997 / 96,096 = 3.1188%"))

        # 20. Active Sellers vs Total Sellers
        active_sellers = conn.execute(text("""
            SELECT COUNT(DISTINCT foi.seller_key)
            FROM fact_order_items foi
            JOIN fact_orders fo ON foi.order_id = fo.order_id
            WHERE fo.order_status = 'delivered';
        """)).scalar()
        total_sellers = conn.execute(text("SELECT COUNT(DISTINCT seller_key) FROM dim_sellers;")).scalar()
        results.append(("Active Sellers", "Merchants fulfilling at least 1 delivered order", active_sellers, "sellers", "2,970 active merchants (with delivered sales)"))
        results.append(("Total Sellers", "All registered merchants in catalog", total_sellers, "sellers", "3,095 total merchants in dim_sellers"))

        # 21. Category Delivered Orders (Sample 3 categories)
        cat_sample = conn.execute(text("""
            SELECT dp.category_name_english, COUNT(DISTINCT foi.order_id) AS cat_orders
            FROM fact_order_items foi
            JOIN fact_orders fo ON foi.order_id = fo.order_id
            JOIN dim_products dp ON foi.product_key = dp.product_key
            WHERE fo.order_status = 'delivered'
              AND dp.category_name_english IN ('bed_bath_table', 'health_beauty', 'watches_gifts')
            GROUP BY dp.category_name_english;
        """)).mappings().all()
        for r in cat_sample:
            results.append((f"Delivered Orders ({r['category_name_english']})", "Category-aware distinct delivered orders", r['cat_orders'], "orders", "FactOrderItems grain with delivered filter"))

    df = pd.DataFrame(results, columns=["Metric Name", "Business Definition", "PostgreSQL Value", "Unit", "DAX / SQL Reconciliation Proof"])
    print("\n" + "=" * 100)
    print("COMMERCELENS AI — POWER BI MEASURE RECONCILIATION AUDIT")
    print("=" * 100)
    for idx, row in df.iterrows():
        print(f"{row['Metric Name']:<32} | {str(row['PostgreSQL Value']):<18} | {row['DAX / SQL Reconciliation Proof']}")
    print("=" * 100)

    # Sanity Assertions
    assert total_orders == 99441, f"Expected 99,441 orders, got {total_orders}"
    assert delivered_orders == 96478, f"Expected 96,478 delivered, got {delivered_orders}"
    assert sla_eligible == 96470, f"Expected 96,470 SLA eligible, got {sla_eligible}"
    assert missing_ts == 8, f"Expected 8 missing timestamps, got {missing_ts}"
    assert on_time == 88644, f"Expected 88,644 on-time, got {on_time}"
    assert late == 7826, f"Expected 7,826 late, got {late}"
    assert otdr == 91.89, f"Expected 91.89% OTDR, got {otdr}"
    assert unique_users == 96096, f"Expected 96,096 unique customers, got {unique_users}"
    assert repeat_users == 2997, f"Expected 2,997 repeat customers, got {repeat_users}"
    assert active_sellers == 2970, f"Expected 2,970 active sellers, got {active_sellers}"
    assert total_sellers == 3095, f"Expected 3,095 total sellers, got {total_sellers}"

    # CSAT Assertions and Sign Consistency Check
    assert float(avg_csat) == 4.09, f"Expected 4.09 average CSAT, got {avg_csat}"
    assert float(on_time_csat) == 4.29, f"Expected 4.29 on-time CSAT, got {on_time_csat}"
    assert float(late_csat) == 2.57, f"Expected 2.57 late CSAT, got {late_csat}"
    assert csat_penalty == -1.73, f"Expected -1.73 CSAT penalty, got {csat_penalty}"
    assert csat_gap == 1.73, f"Expected +1.73 CSAT gap, got {csat_gap}"

    # Forensic Historical CSAT Reconciliation (2.26 vs 2.57 stars)
    with engine.connect() as conn:
        ts_late = conn.execute(text("""
            SELECT COUNT(fr.review_id) AS cnt, ROUND(AVG(fr.review_score), 4) AS mean_score
            FROM fact_reviews fr
            JOIN fact_orders fo ON fr.order_id = fo.order_id
            WHERE fo.is_eligible_for_sla = TRUE AND fo.is_late = TRUE;
        """)).mappings().first()
        assert ts_late['cnt'] == 7700
        assert round(float(ts_late['mean_score']), 2) == 2.57

        cal_late = conn.execute(text("""
            SELECT COUNT(fr.review_id) AS cnt, ROUND(AVG(fr.review_score), 4) AS mean_score
            FROM fact_reviews fr
            JOIN fact_orders fo ON fr.order_id = fo.order_id
            WHERE fo.is_eligible_for_sla = TRUE 
              AND fo.order_delivered_customer_date::DATE > fo.order_estimated_delivery_date::DATE;
        """)).mappings().first()
        assert cal_late['cnt'] == 6409
        assert round(float(cal_late['mean_score']), 2) == 2.27  # Historical Phase 2A exploratory value (~2.26-2.27)

        same_day_late = conn.execute(text("""
            SELECT COUNT(fr.review_id) AS cnt, ROUND(AVG(fr.review_score), 4) AS mean_score
            FROM fact_reviews fr
            JOIN fact_orders fo ON fr.order_id = fo.order_id
            WHERE fo.is_eligible_for_sla = TRUE 
              AND fo.order_delivered_customer_date::DATE = fo.order_estimated_delivery_date::DATE
              AND fo.order_delivered_customer_date > fo.order_estimated_delivery_date;
        """)).mappings().first()
        assert same_day_late['cnt'] == 1291
        assert round(float(same_day_late['mean_score']), 2) == 4.03
        assert ts_late['cnt'] == cal_late['cnt'] + same_day_late['cnt'], "7,700 late reviews must reconcile to 6,409 + 1,291"

    print("\n>>> ALL RECONCILIATION SANITY ASSERTIONS PASSED (100% ACCURACY) <<<")
    return df


if __name__ == "__main__":
    verify_all_measures()

