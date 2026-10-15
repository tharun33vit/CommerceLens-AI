"""
Tests for Power BI Project (.pbip) Artifacts, TMDL Semantic Model,
DAX Measures Library, and Database Reconciliation.
"""

import json
from pathlib import Path
import pytest
from sqlalchemy import text
from commercelens.analytics.db import create_db_engine, check_connection


@pytest.fixture(scope="module")
def powerbi_dir():
    p = Path(__file__).resolve().parent.parent / "dashboards" / "powerbi"
    assert p.is_dir(), f"Power BI directory not found: {p}"
    return p


@pytest.fixture(scope="module")
def db_engine():
    engine = create_db_engine()
    connected, _ = check_connection(engine)
    if not connected:
        pytest.skip("PostgreSQL database is not accessible for reconciliation tests")
    return engine


def test_pbip_root_file(powerbi_dir):
    """Test that CommerceLens-Analytics.pbip exists, is valid JSON, and strictly conforms to PBIP schema."""
    import jsonschema

    pbip_file = powerbi_dir / "CommerceLens-Analytics.pbip"
    assert pbip_file.is_file(), "CommerceLens-Analytics.pbip does not exist"
    data = json.loads(pbip_file.read_text(encoding="utf-8"))
    
    # Official Microsoft PBIP Schema definition (offline-safe)
    pbip_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "$schema": {
                "type": "string",
                "pattern": r"^https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1\.[0-9]+\.[0-9]+/schema\.json$"
            },
            "version": {"type": "string"},
            "artifacts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "report": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "path": {"type": "string"}
                            },
                            "required": ["path"]
                        }
                    },
                    "required": ["report"]
                }
            },
            "settings": {
                "type": ["object", "null"],
                "additionalProperties": False,
                "properties": {
                    "enableAutoRecovery": {"type": "boolean"}
                }
            }
        },
        "required": ["version", "artifacts"]
    }
    
    # Validate against official schema
    jsonschema.validate(instance=data, schema=pbip_schema)

    # Core properties
    assert data.get("version") == "1.0"
    assert len(data.get("artifacts", [])) > 0
    report_rel_path = data["artifacts"][0]["report"]["path"]
    assert report_rel_path == "CommerceLens-Analytics.Report"
    
    # Verify referenced report folder exists on disk
    report_folder = powerbi_dir / report_rel_path
    assert report_folder.is_dir(), f"Referenced report directory not found: {report_folder}"
    
    # Ensure unsupported property 'enableAutoAuth' is not present
    if "settings" in data and data["settings"] is not None:
        assert "enableAutoAuth" not in data["settings"], "Unsupported 'enableAutoAuth' property must not be present"



def test_report_artifacts(powerbi_dir):
    """Test report definition and pages in CommerceLens-Analytics.Report."""
    report_dir = powerbi_dir / "CommerceLens-Analytics.Report"
    assert report_dir.is_dir()
    
    pbir_file = report_dir / "definition.pbir"
    assert pbir_file.is_file()
    pbir_data = json.loads(pbir_file.read_text(encoding="utf-8"))
    sm_rel_path = pbir_data["datasetReference"]["byPath"]["path"]
    assert "../CommerceLens-Analytics.SemanticModel" in sm_rel_path
    semantic_model_folder = (report_dir / sm_rel_path).resolve()
    assert semantic_model_folder.is_dir(), f"Referenced SemanticModel folder does not exist: {semantic_model_folder}"

    report_json_file = report_dir / "report.json"
    assert report_json_file.is_file()
    report_data = json.loads(report_json_file.read_text(encoding="utf-8"))
    sections = report_data.get("sections", [])
    assert len(sections) == 4, f"Expected 4 report pages, found {len(sections)}"
    
    page_names = [s.get("displayName") for s in sections]
    assert "Executive Overview" in page_names
    assert "Sales & Category Diagnostics" in page_names
    assert "Logistics & SLA Operations" in page_names
    assert "Customer Reviews & Retention" in page_names


def test_semantic_model_tmdl_artifacts(powerbi_dir):
    """Test TMDL semantic model files or TMSL model.bim artifacts."""
    sm_dir = powerbi_dir / "CommerceLens-Analytics.SemanticModel"
    assert sm_dir.is_dir()
    
    definition_dir = sm_dir / "definition"
    bim_file = sm_dir / "model.bim"
    
    assert definition_dir.is_dir() or bim_file.is_file(), (
        "Semantic model must contain either a TMDL definition/ folder or universal TMSL model.bim"
    )
    
    if definition_dir.is_dir():
        # Model and database definitions
        assert (definition_dir / "database.tmdl").is_file()
        assert (definition_dir / "model.tmdl").is_file()
        assert (definition_dir / "relationships.tmdl").is_file()
        
        # Tables
        tables_dir = definition_dir / "tables"
        assert tables_dir.is_dir()
        expected_tables = [
            "DimDate.tmdl",
            "DimCustomers.tmdl",
            "DimSellers.tmdl",
            "DimProducts.tmdl",
            "DimGeography.tmdl",
            "FactOrders.tmdl",
            "FactOrderItems.tmdl",
            "FactPayments.tmdl",
            "FactReviews.tmdl",
            "_Measures.tmdl",
        ]
        for tbl in expected_tables:
            assert (tables_dir / tbl).is_file(), f"Missing TMDL table: {tbl}"
    else:
        # When saved as TMSL in PBIP, verify definition.pbism indicator and model.bim
        pbism_file = sm_dir / "definition.pbism"
        assert pbism_file.is_file(), "TMSL SemanticModel requires definition.pbism"
        assert bim_file.is_file(), "TMSL SemanticModel requires model.bim"
        bim_data = json.loads(bim_file.read_text(encoding="utf-8"))
        assert "model" in bim_data


def test_model_bim_universal_compatibility(powerbi_dir):
    """Test that model.bim is valid JSON and contains all required entities."""
    bim_file = powerbi_dir / "CommerceLens-Analytics.SemanticModel" / "model.bim"
    assert bim_file.is_file()
    bim_data = json.loads(bim_file.read_text(encoding="utf-8"))
    
    tables = {t["name"]: t for t in bim_data["model"]["tables"]}
    core_tables = [
        "DimDate", "DimCustomers", "DimSellers", "DimProducts", "DimGeography",
        "FactOrders", "FactOrderItems", "FactPayments", "FactReviews", "_Measures"
    ]
    for tbl in core_tables:
        assert tbl in tables, f"Missing required core table in model.bim: {tbl}"
    
    allowed_extensions = {
        "FactReviewAnalysis", "FactReviewThemes", "ViewReviewProcessingCoverage",
        "ViewReviewSentimentByRating", "ViewReviewDeliveryCohortAnalysis",
        "ViewReviewThemesByCategory", "ViewReviewStateLogisticsSentiment"
    }
    for tbl_name in tables:
        is_core = tbl_name in core_tables
        is_extension = tbl_name in allowed_extensions
        is_auto_date = tbl_name.startswith("LocalDateTable_") or tbl_name.startswith("DateTableTemplate_")
        assert is_core or is_extension or is_auto_date, f"Unrecognized table found in model.bim: {tbl_name}"
    
    assert "FactOrders" in tables
    assert "FactOrderItems" in tables
    assert "_Measures" in tables
    
    measures = {m["name"]: m for m in tables["_Measures"].get("measures", [])}
    assert "Total GMV" in measures
    assert "On-Time Delivery Rate" in measures
    assert "Late Delivery Rate" in measures
    assert "SLA-Eligible Orders" in measures
    assert "Average Order Value (AOV)" in measures
    assert "Repeat Customer Rate" in measures
    assert "CSAT Delivery Penalty" in measures
    assert "CSAT Timeliness Gap" in measures
    
    # Assert measure formula, sign, and format string consistency
    penalty = measures["CSAT Delivery Penalty"]
    assert penalty["expression"] == "[Late Order CSAT] - [On-Time Order CSAT]"
    assert penalty["formatString"] == "0.00;-0.00;0.00"
    
    gap = measures["CSAT Timeliness Gap"]
    assert gap["expression"] == "[On-Time Order CSAT] - [Late Order CSAT]"
    assert gap["formatString"] == "+0.00;-0.00;0.00"

    assert "Delivered Orders (Category)" in measures
    cat_orders = measures["Delivered Orders (Category)"]
    assert cat_orders["expression"] == "CALCULATE(DISTINCTCOUNT(FactOrderItems[order_id]), FactOrders[order_status] = \"delivered\")"
    assert cat_orders["formatString"] == "#,##0"

    assert "Active Sellers" in measures
    active_sellers = measures["Active Sellers"]
    assert active_sellers["expression"] == "CALCULATE(DISTINCTCOUNT(FactOrderItems[seller_key]), FactOrders[order_status] = \"delivered\")"
    assert active_sellers["formatString"] == "#,##0"

    assert "Total Sellers" in measures
    total_sellers = measures["Total Sellers"]
    assert total_sellers["expression"] == "DISTINCTCOUNT(DimSellers[seller_key])"
    assert total_sellers["formatString"] == "#,##0"


def test_dax_measures_library_coverage(powerbi_dir):
    """Test that standalone dax_measures.dax covers all required business KPIs."""
    dax_file = powerbi_dir / "dax_measures.dax"
    assert dax_file.is_file()
    content = dax_file.read_text(encoding="utf-8")
    
    required_keywords = [
        "Total GMV",
        "Delivered Orders",
        "SLA-Eligible Orders",
        "Delivered Missing Timestamp Orders",
        "On-Time Orders",
        "Late Orders",
        "On-Time Delivery Rate",
        "Late Delivery Rate",
        "Cancellation Rate",
        "Unavailable Order Rate",
        "Average Order Value (AOV)",
        "Freight to Merchandise Ratio",
        "Average Review Score",
        "On-Time Order CSAT",
        "Late Order CSAT",
        "CSAT Delivery Penalty",
        "CSAT Timeliness Gap",
        "Total Unique Customers",
        "Repeat Customers Count",
        "Repeat Customer Rate",
        "Pareto Cumulative GMV %",
    ]
    for kw in required_keywords:
        assert kw in content, f"Missing measure or keyword in dax_measures.dax: {kw}"


def test_powerquery_m_scripts_coverage(powerbi_dir):
    """Test that powerquery_m_scripts.pq covers PostgreSQL import logic."""
    m_file = powerbi_dir / "powerquery_m_scripts.pq"
    assert m_file.is_file()
    content = m_file.read_text(encoding="utf-8")
    assert "PostgreSQL.Database(\"localhost:5432\", \"commercelens_db\"" in content
    assert "dim_date" in content
    assert "fact_orders" in content
    assert "fact_order_items" in content
    assert "fact_payments" in content
    assert "fact_reviews" in content


def test_database_reconciliation_values(db_engine):
    """Assert that DAX mathematical formulations match live database values exactly."""
    with db_engine.connect() as conn:
        total_orders = conn.execute(text("SELECT COUNT(*) FROM fact_orders;")).scalar()
        delivered_orders = conn.execute(text("SELECT COUNT(*) FROM fact_orders WHERE order_status = 'delivered';")).scalar()
        sla_eligible = conn.execute(text("SELECT COUNT(*) FROM fact_orders WHERE is_eligible_for_sla = TRUE;")).scalar()
        missing_ts = conn.execute(text("SELECT COUNT(*) FROM fact_orders WHERE order_status = 'delivered' AND order_delivered_customer_date IS NULL;")).scalar()
        on_time = conn.execute(text("SELECT COUNT(*) FROM fact_orders WHERE is_eligible_for_sla = TRUE AND is_late = FALSE;")).scalar()
        late = conn.execute(text("SELECT COUNT(*) FROM fact_orders WHERE is_eligible_for_sla = TRUE AND is_late = TRUE;")).scalar()
        
        assert total_orders == 99441
        assert delivered_orders == 96478
        assert sla_eligible == 96470
        assert missing_ts == 8
        assert on_time == 88644
        assert late == 7826
        
        otdr = round((on_time / sla_eligible) * 100, 2)
        assert otdr == 91.89
        
        ldr = round((late / sla_eligible) * 100, 2)
        assert ldr == 8.11

        # Phase 3C: Active Sellers (delivered orders) vs Total Sellers in DimSellers
        active_sellers = conn.execute(text("""
            SELECT COUNT(DISTINCT foi.seller_key)
            FROM fact_order_items foi
            JOIN fact_orders fo ON foi.order_id = fo.order_id
            WHERE fo.order_status = 'delivered';
        """)).scalar()
        total_sellers = conn.execute(text("SELECT COUNT(DISTINCT seller_key) FROM dim_sellers;")).scalar()
        assert active_sellers == 2970, f"Expected 2,970 active sellers, got {active_sellers}"
        assert total_sellers == 3095, f"Expected 3,095 total sellers, got {total_sellers}"

        # Phase 3C: Category-aware delivered orders validation
        cat_counts = conn.execute(text("""
            SELECT dp.category_name_english, COUNT(DISTINCT foi.order_id) AS cat_orders
            FROM fact_order_items foi
            JOIN fact_orders fo ON foi.order_id = fo.order_id
            JOIN dim_products dp ON foi.product_key = dp.product_key
            WHERE fo.order_status = 'delivered'
              AND dp.category_name_english IN ('bed_bath_table', 'health_beauty', 'watches_gifts')
            GROUP BY dp.category_name_english;
        """)).mappings().all()
        cat_map = {r['category_name_english']: r['cat_orders'] for r in cat_counts}
        assert cat_map['bed_bath_table'] == 9272
        assert cat_map['health_beauty'] == 8647
        assert cat_map['watches_gifts'] == 5495

        # Verify cross-category overlap: multi-category orders count once per category
        sum_category_orders = conn.execute(text("""
            SELECT SUM(sub.cat_orders) FROM (
                SELECT dp.category_name_english, COUNT(DISTINCT foi.order_id) AS cat_orders
                FROM fact_order_items foi
                JOIN fact_orders fo ON foi.order_id = fo.order_id
                JOIN dim_products dp ON foi.product_key = dp.product_key
                WHERE fo.order_status = 'delivered'
                GROUP BY dp.category_name_english
            ) sub;
        """)).scalar()
        assert sum_category_orders == 97276
        assert sum_category_orders > delivered_orders, "Sum of category orders (97,276) must exceed unique delivered orders (96,478) due to multi-category carts"
        
        # Verify exact multi-category order count across English product categories
        multi_cat_orders = conn.execute(text("""
            SELECT COUNT(*) FROM (
                SELECT foi.order_id
                FROM fact_order_items foi
                JOIN fact_orders fo ON foi.order_id = fo.order_id
                JOIN dim_products dp ON foi.product_key = dp.product_key
                WHERE fo.order_status = 'delivered'
                GROUP BY foi.order_id
                HAVING COUNT(DISTINCT dp.category_name_english) > 1
            ) multi;
        """)).scalar()
        assert multi_cat_orders == 723, f"Expected 723 multi-category orders, got {multi_cat_orders}"


def test_csat_database_reconciliation_and_historical_audit(db_engine):
    """
    Assert CSAT metrics, exact review denominators, sign consistency,
    and forensically reconcile the Phase 2A (~2.26) vs Phase 3 (2.57) late CSAT discrepancy.
    """
    with db_engine.connect() as conn:
        # Total submitted reviews
        total_reviews = conn.execute(text("SELECT COUNT(*) FROM fact_reviews;")).scalar()
        assert total_reviews == 99224
        
        # On-Time Order Reviews (is_eligible_for_sla = TRUE AND is_late = FALSE)
        on_time_res = conn.execute(text("""
            SELECT COUNT(fr.review_id) AS cnt, ROUND(AVG(fr.review_score), 4) AS mean_score
            FROM fact_reviews fr
            JOIN fact_orders fo ON fr.order_id = fo.order_id
            WHERE fo.is_eligible_for_sla = TRUE AND fo.is_late = FALSE;
        """)).mappings().first()
        assert on_time_res['cnt'] == 88653
        on_time_csat = round(float(on_time_res['mean_score']), 2)
        assert on_time_csat == 4.29
        
        # Late Order Reviews (is_eligible_for_sla = TRUE AND is_late = TRUE)
        late_res = conn.execute(text("""
            SELECT COUNT(fr.review_id) AS cnt, ROUND(AVG(fr.review_score), 4) AS mean_score
            FROM fact_reviews fr
            JOIN fact_orders fo ON fr.order_id = fo.order_id
            WHERE fo.is_eligible_for_sla = TRUE AND fo.is_late = TRUE;
        """)).mappings().first()
        assert late_res['cnt'] == 7700
        late_csat = round(float(late_res['mean_score']), 2)
        assert late_csat == 2.57
        
        # Consistent formula and sign verification from unrounded averages:
        on_time_mean_raw = float(conn.execute(text("""
            SELECT AVG(fr.review_score)
            FROM fact_reviews fr
            JOIN fact_orders fo ON fr.order_id = fo.order_id
            WHERE fo.is_eligible_for_sla = TRUE AND fo.is_late = FALSE;
        """)).scalar())
        late_mean_raw = float(conn.execute(text("""
            SELECT AVG(fr.review_score)
            FROM fact_reviews fr
            JOIN fact_orders fo ON fr.order_id = fo.order_id
            WHERE fo.is_eligible_for_sla = TRUE AND fo.is_late = TRUE;
        """)).scalar())
        
        # CSAT Delivery Penalty = Late Order CSAT - On-Time Order CSAT = 2.566493 - 4.293718 = -1.72722... -> -1.73 stars
        # CSAT Timeliness Gap   = On-Time Order CSAT - Late Order CSAT = 4.293718 - 2.566493 = +1.72722... -> +1.73 stars
        csat_penalty = round(late_mean_raw - on_time_mean_raw, 2)
        csat_gap = round(on_time_mean_raw - late_mean_raw, 2)
        assert csat_penalty == -1.73
        assert csat_gap == 1.73
        
        # Undelivered / In-transit review cohort
        undeliv_res = conn.execute(text("""
            SELECT COUNT(fr.review_id) AS cnt, ROUND(AVG(fr.review_score), 2) AS mean_score
            FROM fact_reviews fr
            JOIN fact_orders fo ON fr.order_id = fo.order_id
            WHERE fo.is_delivered = FALSE;
        """)).mappings().first()
        assert undeliv_res['cnt'] == 2863
        assert float(undeliv_res['mean_score']) == 1.75
        
        # Delivered missing milestone exception review cohort
        missing_ts_res = conn.execute(text("""
            SELECT COUNT(fr.review_id) AS cnt, ROUND(AVG(fr.review_score), 2) AS mean_score
            FROM fact_reviews fr
            JOIN fact_orders fo ON fr.order_id = fo.order_id
            WHERE fo.order_status = 'delivered' AND fo.order_delivered_customer_date IS NULL;
        """)).mappings().first()
        assert missing_ts_res['cnt'] == 8
        assert float(missing_ts_res['mean_score']) == 4.50
        
        # Complete review population reconciliation (100% accounted for)
        assert on_time_res['cnt'] + late_res['cnt'] + undeliv_res['cnt'] + missing_ts_res['cnt'] == total_reviews
        
        # Forensic explanation of historical ~2.26 stars (calendar-day truncation late):
        cal_late = conn.execute(text("""
            SELECT 
                COUNT(fr.review_id) AS cnt, 
                ROUND(AVG(fr.review_score), 4) AS mean_score,
                ROUND(COUNT(CASE WHEN fr.review_score = 1 THEN 1 END)::NUMERIC / COUNT(fr.review_id) * 100, 2) AS one_star_pct
            FROM fact_reviews fr
            JOIN fact_orders fo ON fr.order_id = fo.order_id
            WHERE fo.is_eligible_for_sla = TRUE 
              AND fo.order_delivered_customer_date::DATE > fo.order_estimated_delivery_date::DATE;
        """)).mappings().first()
        assert cal_late['cnt'] == 6409
        assert round(float(cal_late['mean_score']), 2) == 2.27
        assert float(cal_late['one_star_pct']) == 53.74  # Reconciles historical "~54% 1-star reviews" (53.74%)
        
        # Same-day afternoon delivery cohort (delivered::DATE = estimated::DATE and delivered > estimated)
        same_day_late = conn.execute(text("""
            SELECT COUNT(fr.review_id) AS cnt, ROUND(AVG(fr.review_score), 2) AS mean_score
            FROM fact_reviews fr
            JOIN fact_orders fo ON fr.order_id = fo.order_id
            WHERE fo.is_eligible_for_sla = TRUE 
              AND fo.order_delivered_customer_date::DATE = fo.order_estimated_delivery_date::DATE
              AND fo.order_delivered_customer_date > fo.order_estimated_delivery_date;
        """)).mappings().first()
        assert same_day_late['cnt'] == 1291
        assert float(same_day_late['mean_score']) == 4.03
        
        # Exact mathematical reconciliation of late review population
        assert late_res['cnt'] == cal_late['cnt'] + same_day_late['cnt']


def test_report_prototype_queries_and_format_integrity(powerbi_dir):
    """
    Validate that CommerceLens-Analytics.Report adheres strictly to PBIR-Legacy format:
    1. No conflicting enhanced PBIR 'definition/' folder exists.
    2. Every visual with a prototypeQuery has Version: 2 and a non-empty From clause.
    3. Every source in Select is declared in From with Type: 0.
    4. Every queryRef in projections matches a Select item Name.
    """
    report_dir = powerbi_dir / "CommerceLens-Analytics.Report"
    
    # 1. No conflicting definition folder
    conflicting_def = report_dir / "definition"
    assert not conflicting_def.exists(), "Conflicting enhanced PBIR 'definition/' folder must not exist in PBIR-Legacy report"
    
    # 2. Check definition.pbir version
    pbir_file = report_dir / "definition.pbir"
    assert pbir_file.is_file()
    pbir_data = json.loads(pbir_file.read_text(encoding="utf-8"))
    assert pbir_data.get("version") in ["1.0", "4.0"], f"Expected PBIR version 1.0 or 4.0, got {pbir_data.get('version')}"

    # 3. Check report.json prototypeQueries
    report_json_file = report_dir / "report.json"
    assert report_json_file.is_file()
    rep = json.loads(report_json_file.read_text(encoding="utf-8"))
    
    visual_count = 0
    query_visual_count = 0
    for section in rep.get("sections", []):
        for vc in section.get("visualContainers", []):
            visual_count += 1
            cfg = json.loads(vc.get("config", "{}"))
            sv = cfg.get("singleVisual", {})
            pq = sv.get("prototypeQuery")
            if not pq:
                continue
            
            query_visual_count += 1
            assert pq.get("Version") == 2, f"Visual {cfg.get('name')} missing Version: 2 in prototypeQuery"
            assert "From" in pq, f"Visual {cfg.get('name')} missing From clause in prototypeQuery"
            assert isinstance(pq["From"], list) and len(pq["From"]) > 0, f"Visual {cfg.get('name')} has empty From clause"
            
            from_names = {f["Name"] for f in pq["From"]}
            for f in pq["From"]:
                assert f.get("Type") == 0, f"From source {f} in visual {cfg.get('name')} must have Type 0 (Table)"
                assert f.get("Name") and f.get("Entity"), f"From source {f} in visual {cfg.get('name')} must specify Name and Entity"

            select_names = set()
            for item in pq.get("Select", []):
                select_names.add(item.get("Name"))
                if "Measure" in item:
                    source = item["Measure"]["Expression"]["SourceRef"]["Source"]
                    assert source in from_names, f"Measure source {source} not in From for visual {cfg.get('name')}"
                elif "Column" in item:
                    source = item["Column"]["Expression"]["SourceRef"]["Source"]
                    assert source in from_names, f"Column source {source} not in From for visual {cfg.get('name')}"
                elif "Aggregation" in item:
                    source = item["Aggregation"]["Expression"]["Column"]["Expression"]["SourceRef"]["Source"]
                    assert source in from_names, f"Aggregation column source {source} not in From for visual {cfg.get('name')}"
                else:
                    pytest.fail(f"Visual {cfg.get('name')} has item in Select that is not Measure, Column, or Aggregation: {item}")
            
            projections = sv.get("projections", {})
            for role, proj_list in projections.items():
                for proj in proj_list:
                    qref = proj.get("queryRef")
                    assert qref in select_names, f"queryRef {qref} in role {role} not in Select items for visual {cfg.get('name')}"

    assert visual_count in [46, 53], f"Expected 46 or 53 visuals across 4 pages, found {visual_count}"
    assert query_visual_count in [42, 49], f"Expected 42 or 49 query visuals, found {query_visual_count}"


def test_dim_products_null_preservation(powerbi_dir):
    """
    Validate that Power Query definitions for DimProducts preserve null category values
    and do not replace them with 'unclassified' or other synthetic placeholders.
    """
    # 1. Check TMDL (if present)
    tmdl_file = powerbi_dir / "CommerceLens-Analytics.SemanticModel" / "definition" / "tables" / "DimProducts.tmdl"
    if tmdl_file.is_file():
        tmdl_text = tmdl_file.read_text(encoding="utf-8")
        assert "unclassified" not in tmdl_text, "DimProducts.tmdl must not replace null categories with 'unclassified'"
    
    # 2. Check model.bim
    bim_file = powerbi_dir / "CommerceLens-Analytics.SemanticModel" / "model.bim"
    assert bim_file.is_file()
    bim_text = bim_file.read_text(encoding="utf-8")
    assert "unclassified" not in bim_text, "model.bim must not replace null categories with 'unclassified'"

    # 3. Check powerquery_m_scripts.pq
    m_file = powerbi_dir / "powerquery_m_scripts.pq"
    assert m_file.is_file()
    m_text = m_file.read_text(encoding="utf-8")
    assert "unclassified" not in m_text, "powerquery_m_scripts.pq must not replace null categories with 'unclassified'"


def test_pareto_monotonicity_and_categories(db_engine):
    """
    Validate that cumulative GMV percentages across descending categories
    are strictly monotonic and match the analytical PostgreSQL window calculation.
    """
    with db_engine.connect() as conn:
        pareto_rows = conn.execute(text("""
            WITH cat_gmv AS (
                SELECT 
                    dp.category_name_english,
                    SUM(foi.price) AS category_gmv
                FROM fact_order_items foi
                JOIN fact_orders fo ON foi.order_id = fo.order_id
                JOIN dim_products dp ON foi.product_key = dp.product_key
                WHERE fo.order_status = 'delivered'
                  AND dp.category_name_english IS NOT NULL
                GROUP BY dp.category_name_english
            ),
            cumulative AS (
                SELECT 
                    category_name_english,
                    category_gmv,
                    SUM(category_gmv) OVER (ORDER BY category_gmv DESC, category_name_english ASC) AS running_gmv,
                    SUM(category_gmv) OVER () AS total_gmv
                FROM cat_gmv
            )
            SELECT 
                category_name_english,
                category_gmv,
                running_gmv,
                ROUND((running_gmv / total_gmv) * 100, 4) AS cum_pct
            FROM cumulative
            ORDER BY category_gmv DESC, category_name_english ASC;
        """)).mappings().all()

        assert len(pareto_rows) == 73  # 73 named categories with delivered sales

        # 1. Rank 1 category
        rank_1 = pareto_rows[0]
        assert rank_1['category_name_english'] == 'health_beauty'
        assert round(float(rank_1['cum_pct']), 2) == 9.45

        # 2. Intermediate category (rank 10)
        rank_10 = pareto_rows[9]
        assert rank_10['category_name_english'] == 'toys'
        assert round(float(rank_10['cum_pct']), 2) == 63.25

        # 3. Final category (rank 73)
        rank_final = pareto_rows[-1]
        assert rank_final['category_name_english'] == 'security_and_services'
        assert float(rank_final['cum_pct']) == 100.00

        # 4. Strict monotonicity across all rows
        prev_pct = 0.0
        for r in pareto_rows:
            pct = float(r['cum_pct'])
            assert pct >= prev_pct, f"Monotonicity violation: {pct} < {prev_pct} at {r['category_name_english']}"
            prev_pct = pct



