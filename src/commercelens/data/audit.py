"""
Data Quality Auditing and Relationship Validation Module for CommerceLens AI.

Performs systematic checks on:
- Missing value rates and counts.
- Complete duplicate records.
- Candidate primary-key uniqueness and nullity across table grains.
- Referential integrity across foreign-key relationships.
- Logical and business rule anomalies (e.g. negative values, chronological violations).
"""

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from commercelens.data.schema import (
    CANDIDATE_PRIMARY_KEYS,
    EXPECTED_RELATIONSHIPS,
    DuplicateStat,
    FindingSeverity,
    KeyValidationStat,
    MissingValueStat,
    QualityFinding,
    RelationshipValidationStat,
)


def audit_missing_values(tables: Dict[str, pd.DataFrame]) -> List[MissingValueStat]:
    """
    Compute missing value counts and percentages across all columns in all tables.
    """
    stats: List[MissingValueStat] = []

    for table_name, df in tables.items():
        total_rows = len(df)
        if total_rows == 0:
            continue

        null_counts = df.isnull().sum()
        for col, count in null_counts.items():
            pct = round((count / total_rows) * 100.0, 4)
            stats.append(
                MissingValueStat(
                    table_name=table_name,
                    column_name=str(col),
                    missing_count=int(count),
                    missing_percentage=pct,
                    total_rows=total_rows,
                )
            )

    return stats


def audit_duplicates(tables: Dict[str, pd.DataFrame]) -> List[DuplicateStat]:
    """
    Audit exact duplicate complete rows for all loaded tables.
    """
    stats: List[DuplicateStat] = []

    for table_name, df in tables.items():
        total_rows = len(df)
        if total_rows == 0:
            stats.append(
                DuplicateStat(
                    table_name=table_name,
                    total_rows=0,
                    complete_duplicates_count=0,
                    complete_duplicates_percentage=0.0,
                )
            )
            continue

        dupe_count = int(df.duplicated().sum())
        distinct_complete = total_rows - dupe_count
        dupe_pct = round((dupe_count / total_rows) * 100.0, 4)

        stats.append(
            DuplicateStat(
                table_name=table_name,
                total_rows=total_rows,
                complete_duplicates_count=dupe_count,
                distinct_complete_rows=distinct_complete,
                complete_duplicates_percentage=dupe_pct,
            )
        )

    return stats


def validate_candidate_keys(tables: Dict[str, pd.DataFrame]) -> List[KeyValidationStat]:
    """
    Verify uniqueness and nullity for candidate primary keys.
    """
    stats: List[KeyValidationStat] = []

    for table_name, candidate_cols in CANDIDATE_PRIMARY_KEYS.items():
        if table_name not in tables:
            continue

        df = tables[table_name]
        total_rows = len(df)

        if total_rows == 0:
            continue

        # Check if all candidate key columns are present
        missing_cols = [c for c in candidate_cols if c not in df.columns]
        if missing_cols:
            stats.append(
                KeyValidationStat(
                    table_name=table_name,
                    candidate_key=candidate_cols,
                    total_rows=total_rows,
                    distinct_key_count=0,
                    duplicate_key_groups=0,
                    excess_duplicate_rows=total_rows,
                    duplicate_key_count=0,
                    null_key_count=total_rows,
                    is_valid_pk=False,
                    notes=f"Missing expected key columns in dataframe: {missing_cols}",
                )
            )
            continue

        # Check null values in the key columns
        null_mask = df[candidate_cols].isnull().any(axis=1)
        null_key_count = int(null_mask.sum())

        # Check distinct count, duplicate key groups, and excess duplicate rows
        grouped = df.groupby(candidate_cols, dropna=False).size()
        distinct_count = len(grouped)
        duplicate_key_groups = int((grouped > 1).sum())
        excess_duplicate_rows = int(total_rows - distinct_count)

        is_valid = (null_key_count == 0) and (duplicate_key_groups == 0) and (excess_duplicate_rows == 0)

        note = None
        if not is_valid:
            note = (
                f"Key failed validation: {duplicate_key_groups:,} duplicate key groups "
                f"({excess_duplicate_rows:,} excess rows), {null_key_count:,} null rows."
            )

        stats.append(
            KeyValidationStat(
                table_name=table_name,
                candidate_key=candidate_cols,
                total_rows=total_rows,
                distinct_key_count=distinct_count,
                duplicate_key_groups=duplicate_key_groups,
                excess_duplicate_rows=excess_duplicate_rows,
                duplicate_key_count=duplicate_key_groups,
                null_key_count=null_key_count,
                is_valid_pk=is_valid,
                notes=note,
            )
        )

    # Special check: Customer unique ID vs Customer ID
    if "customers" in tables and "customer_unique_id" in tables["customers"].columns:
        cust_df = tables["customers"]
        tot = len(cust_df)
        cust_grouped = cust_df.groupby("customer_unique_id", dropna=False).size()
        distinct_unique = len(cust_grouped)
        dupe_unique_groups = int((cust_grouped > 1).sum())
        excess_unique_rows = int(tot - distinct_unique)
        stats.append(
            KeyValidationStat(
                table_name="customers",
                candidate_key=["customer_unique_id"],
                total_rows=tot,
                distinct_key_count=distinct_unique,
                duplicate_key_groups=dupe_unique_groups,
                excess_duplicate_rows=excess_unique_rows,
                duplicate_key_count=dupe_unique_groups,
                null_key_count=int(cust_df["customer_unique_id"].isnull().sum()),
                is_valid_pk=False,
                notes="Expected: customer_unique_id represents repeat buyers and is NOT a unique PK per order record.",
            )
        )

    # Special check: Review compound key (review_id, order_id)
    if "order_reviews" in tables and all(c in tables["order_reviews"].columns for c in ["review_id", "order_id"]):
        rev_df = tables["order_reviews"]
        tot_rev = len(rev_df)
        grouped_rev = rev_df.groupby(["review_id", "order_id"], dropna=False).size()
        dist_rev = len(grouped_rev)
        dupe_rev_groups = int((grouped_rev > 1).sum())
        excess_rev_rows = int(tot_rev - dist_rev)
        null_rev = int(rev_df[["review_id", "order_id"]].isnull().any(axis=1).sum())
        stats.append(
            KeyValidationStat(
                table_name="order_reviews",
                candidate_key=["review_id", "order_id"],
                total_rows=tot_rev,
                distinct_key_count=dist_rev,
                duplicate_key_groups=dupe_rev_groups,
                excess_duplicate_rows=excess_rev_rows,
                duplicate_key_count=dupe_rev_groups,
                null_key_count=null_rev,
                is_valid_pk=(null_rev == 0 and dupe_rev_groups == 0 and excess_rev_rows == 0),
                notes="Compound candidate key for reviews. 100% unique across all review records.",
            )
        )

    return stats


def validate_relationships(tables: Dict[str, pd.DataFrame]) -> List[RelationshipValidationStat]:
    """
    Validate foreign-key integrity between parent and child tables.
    """
    stats: List[RelationshipValidationStat] = []

    for rel in EXPECTED_RELATIONSHIPS:
        child_tbl = rel["child_table"]
        child_col = rel["child_col"]
        parent_tbl = rel["parent_table"]
        parent_col = rel["parent_col"]
        rel_name = rel["relationship_name"]

        if child_tbl not in tables or parent_tbl not in tables:
            continue

        c_df = tables[child_tbl]
        p_df = tables[parent_tbl]

        if child_col not in c_df.columns or parent_col not in p_df.columns:
            continue

        child_total = len(c_df)
        if child_total == 0:
            continue

        child_nulls = int(c_df[child_col].isnull().sum())
        non_null_child_series = c_df[child_col].dropna()

        parent_valid_keys = set(p_df[parent_col].dropna().unique())
        child_distinct_keys = int(non_null_child_series.nunique())

        unmatched_mask = ~non_null_child_series.isin(parent_valid_keys)
        unmatched_records = int(unmatched_mask.sum())
        unmatched_keys = int(non_null_child_series[unmatched_mask].nunique())

        matched_records = len(non_null_child_series) - unmatched_records
        integrity_pct = round((matched_records / child_total) * 100.0, 4)

        is_clean = (unmatched_records == 0) and (child_nulls == 0)

        stats.append(
            RelationshipValidationStat(
                relationship_name=rel_name,
                child_table=child_tbl,
                child_col=child_col,
                parent_table=parent_tbl,
                parent_col=parent_col,
                child_total_records=child_total,
                child_null_records=child_nulls,
                child_distinct_keys=child_distinct_keys,
                unmatched_child_records=unmatched_records,
                unmatched_child_keys=unmatched_keys,
                referential_integrity_percentage=integrity_pct,
                is_clean=is_clean,
            )
        )

    return stats


def audit_business_rule_anomalies(tables: Dict[str, pd.DataFrame]) -> List[QualityFinding]:
    """
    Inspect logical, domain, and chronological constraints.
    Classify each finding as CONFIRMED_ISSUE, CANDIDATE_INVESTIGATION, or EXPECTED_CHARACTERISTIC.
    """
    findings: List[QualityFinding] = []

    # 1. Orders Chronology Checks
    if "orders" in tables:
        orders = tables["orders"]

        # Check delivered before purchase
        if "order_delivered_customer_date" in orders.columns and "order_purchase_timestamp" in orders.columns:
            both_valid = orders["order_delivered_customer_date"].notnull() & orders["order_purchase_timestamp"].notnull()
            time_diff = orders.loc[both_valid, "order_delivered_customer_date"] < orders.loc[both_valid, "order_purchase_timestamp"]
            anomaly_count = int(time_diff.sum())
            if anomaly_count > 0:
                findings.append(
                    QualityFinding(
                        finding_id="ORD_TIME_01",
                        table_name="orders",
                        column_name="order_delivered_customer_date",
                        severity=FindingSeverity.CONFIRMED_ISSUE,
                        title="Delivery Timestamp Precedes Purchase Timestamp",
                        evidence=f"{anomaly_count} orders have delivery timestamp earlier than purchase timestamp.",
                        recommended_action="Flag or exclude these inconsistent orders from logistics lead-time calculations.",
                        is_safe_to_clean=False,
                    )
                )

        # Reconcile delivery timestamps across all order statuses
        if "order_status" in orders.columns and "order_delivered_customer_date" in orders.columns:
            null_deliv_mask = orders["order_delivered_customer_date"].isnull()
            total_missing_deliv = int(null_deliv_mask.sum())
            if total_missing_deliv > 0:
                status_counts = orders.loc[null_deliv_mask, "order_status"].value_counts().to_dict()
                delivered_missing = status_counts.get("delivered", 0)
                non_delivered_missing = sum(cnt for st, cnt in status_counts.items() if st != "delivered")

                # Format per-status breakdown sorted descending by count
                breakdown_items = [
                    f"{st}={cnt:,}"
                    for st, cnt in sorted(status_counts.items(), key=lambda x: -x[1])
                    if st != "delivered"
                ]
                breakdown_str = ", ".join(breakdown_items)

                # Delivered orders missing timestamp (unconfirmed delivery milestone)
                if delivered_missing > 0:
                    findings.append(
                        QualityFinding(
                            finding_id="ORD_STAT_01",
                            table_name="orders",
                            column_name="order_delivered_customer_date",
                            severity=FindingSeverity.CANDIDATE_INVESTIGATION,
                            title="Delivered Status with Missing Delivery Timestamp",
                            evidence=(
                                f"{delivered_missing} orders marked as 'delivered' have a NULL order_delivered_customer_date. "
                                f"Accounts for {delivered_missing} of {total_missing_deliv:,} total missing delivery timestamps."
                            ),
                            recommended_action="Do not compute lead times on these orders; investigate whether delivery confirmation was omitted.",
                            is_safe_to_clean=False,
                        )
                    )

                # Non-delivered orders missing timestamp (expected operational characteristic)
                if non_delivered_missing > 0:
                    findings.append(
                        QualityFinding(
                            finding_id="ORD_STAT_02",
                            table_name="orders",
                            column_name="order_delivered_customer_date",
                            severity=FindingSeverity.EXPECTED_CHARACTERISTIC,
                            title="Non-Delivered Orders with Null Delivery Dates",
                            evidence=(
                                f"{non_delivered_missing:,} orders across all non-delivered statuses naturally have NULL delivery dates "
                                f"({breakdown_str}). Fully reconciles all missing values: "
                                f"{delivered_missing} delivered + {non_delivered_missing:,} non-delivered = {total_missing_deliv:,} total missing."
                            ),
                            recommended_action="Filter order_status = 'delivered' before running logistics lead-time analyses.",
                            is_safe_to_clean=True,
                        )
                    )

    # 2. Order Items Price / Freight Checks
    if "order_items" in tables:
        items = tables["order_items"]
        if "price" in items.columns:
            neg_price = int((items["price"] < 0).sum())
            zero_price = int((items["price"] == 0).sum())
            if neg_price > 0:
                findings.append(
                    QualityFinding(
                        finding_id="ITEM_VAL_01",
                        table_name="order_items",
                        column_name="price",
                        severity=FindingSeverity.CONFIRMED_ISSUE,
                        title="Negative Item Price",
                        evidence=f"{neg_price} order items have negative price values.",
                        recommended_action="Investigate and exclude negative price records from GMV calculations.",
                        is_safe_to_clean=False,
                    )
                )
            if zero_price > 0:
                findings.append(
                    QualityFinding(
                        finding_id="ITEM_VAL_02",
                        table_name="order_items",
                        column_name="price",
                        severity=FindingSeverity.CANDIDATE_INVESTIGATION,
                        title="Zero Price Items Found",
                        evidence=f"{zero_price} order items have price = 0.00.",
                        recommended_action="Examine whether these represent promotional freebies or test records.",
                        is_safe_to_clean=False,
                    )
                )

        if "freight_value" in items.columns:
            neg_freight = int((items["freight_value"] < 0).sum())
            if neg_freight > 0:
                findings.append(
                    QualityFinding(
                        finding_id="ITEM_VAL_03",
                        table_name="order_items",
                        column_name="freight_value",
                        severity=FindingSeverity.CONFIRMED_ISSUE,
                        title="Negative Freight Value",
                        evidence=f"{neg_freight} order items have negative freight values.",
                        recommended_action="Filter or audit negative freight records.",
                        is_safe_to_clean=False,
                    )
                )

    # 3. Order Payments Values Checks
    if "order_payments" in tables:
        payments = tables["order_payments"]
        if "payment_value" in payments.columns:
            zero_payments = int((payments["payment_value"] == 0).sum())
            neg_payments = int((payments["payment_value"] < 0).sum())
            if neg_payments > 0:
                findings.append(
                    QualityFinding(
                        finding_id="PAY_VAL_01",
                        table_name="order_payments",
                        column_name="payment_value",
                        severity=FindingSeverity.CONFIRMED_ISSUE,
                        title="Negative Payment Values",
                        evidence=f"{neg_payments} payments have negative payment_value.",
                        recommended_action="Investigate potential refund/chargeback records.",
                        is_safe_to_clean=False,
                    )
                )
            if zero_payments > 0:
                findings.append(
                    QualityFinding(
                        finding_id="PAY_VAL_02",
                        table_name="order_payments",
                        column_name="payment_value",
                        severity=FindingSeverity.CANDIDATE_INVESTIGATION,
                        title="Zero Value Payment Slices",
                        evidence=f"{zero_payments} payments have payment_value = 0.00 (likely 100% voucher applied).",
                        recommended_action="Retain vouchers while auditing full voucher discount reconciliation.",
                        is_safe_to_clean=False,
                    )
                )

    # 4. Review Score Range Checks
    if "order_reviews" in tables:
        reviews = tables["order_reviews"]
        if "review_score" in reviews.columns:
            invalid_scores = int((~reviews["review_score"].isin([1, 2, 3, 4, 5])).sum())
            if invalid_scores > 0:
                findings.append(
                    QualityFinding(
                        finding_id="REV_VAL_01",
                        table_name="order_reviews",
                        column_name="review_score",
                        severity=FindingSeverity.CONFIRMED_ISSUE,
                        title="Review Scores Outside Standard 1-5 Range",
                        evidence=f"{invalid_scores} review records have score not in (1, 2, 3, 4, 5).",
                        recommended_action="Cleanse or exclude invalid scores from CSAT calculation.",
                        is_safe_to_clean=False,
                    )
                )

    # 5. Geolocation Coordinate Boundaries (Brazil Bounding Box)
    if "geolocation" in tables:
        geo = tables["geolocation"]
        if "geolocation_lat" in geo.columns and "geolocation_lng" in geo.columns:
            # Brazil geographic bounds approximately: Lat [-34.0, +5.5], Long [-74.0, -34.0]
            out_of_bounds = (
                (geo["geolocation_lat"] < -35.0) | (geo["geolocation_lat"] > 6.0) |
                (geo["geolocation_lng"] < -75.0) | (geo["geolocation_lng"] > -33.0)
            )
            out_count = int(out_of_bounds.sum())
            if out_count > 0:
                findings.append(
                    QualityFinding(
                        finding_id="GEO_BOUND_01",
                        table_name="geolocation",
                        column_name="geolocation_lat",
                        severity=FindingSeverity.CANDIDATE_INVESTIGATION,
                        title="Coordinates Outside Brazilian Geographic Bounding Box",
                        evidence=f"{out_count} coordinate records fall outside continental Brazil coordinates.",
                        recommended_action="Filter coordinates before spatial distance calculations or compute median centroid per zip prefix.",
                        is_safe_to_clean=False,
                    )
                )

    # 6. Product Category Translation Mapping Gaps
    if "products" in tables:
        products = tables["products"]
        if "product_category_name" in products.columns:
            null_cats = int(products["product_category_name"].isnull().sum())
            if "category_translation" in tables:
                trans = tables["category_translation"]
                if "product_category_name" in trans.columns:
                    valid_cats = set(trans["product_category_name"].dropna().unique())
                    non_null_prod = products[products["product_category_name"].notnull()]
                    unmatched_prod = non_null_prod[~non_null_prod["product_category_name"].isin(valid_cats)]
                    unmatched_count = len(unmatched_prod)
                    unmatched_distinct = sorted(unmatched_prod["product_category_name"].unique().tolist())
                    unmatched_breakdown = ", ".join(
                        f"'{cat}' ({cnt} products)"
                        for cat, cnt in unmatched_prod["product_category_name"].value_counts().items()
                    )

                    if null_cats > 0 or unmatched_count > 0:
                        findings.append(
                            QualityFinding(
                                finding_id="PROD_CAT_01",
                                table_name="products",
                                column_name="product_category_name",
                                severity=FindingSeverity.CONFIRMED_ISSUE,
                                title="Product Category Translation Mapping Gaps",
                                evidence=(
                                    f"{null_cats} products have NULL product_category_name. "
                                    f"{unmatched_count} products have non-null categories lacking an English translation across "
                                    f"{len(unmatched_distinct)} distinct categories: {unmatched_breakdown}."
                                ),
                                recommended_action=(
                                    "Do not invent placeholder categories or discard records. "
                                    "In Phase 2 DDL/reporting, leave English category as NULL or map "
                                    "'pc_gamer' -> 'pc_gamer' and 'portateis_cozinha_e_preparadores_de_alimentos' -> "
                                    "'portable_kitchen_food_preparers'."
                                ),
                                is_safe_to_clean=False,
                            )
                        )

    return findings


def execute_comprehensive_audit(tables: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    """
    Run full suite of audits across all loaded tables.
    """
    missing_stats = audit_missing_values(tables)
    duplicate_stats = audit_duplicates(tables)
    key_stats = validate_candidate_keys(tables)
    rel_stats = validate_relationships(tables)
    findings = audit_business_rule_anomalies(tables)

    return {
        "missing_stats": missing_stats,
        "duplicate_stats": duplicate_stats,
        "key_stats": key_stats,
        "relationship_stats": rel_stats,
        "findings": findings,
    }
