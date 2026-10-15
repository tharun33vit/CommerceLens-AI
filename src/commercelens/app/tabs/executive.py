"""
CommerceLens AI — Executive Analytics Dashboard Tab
===================================================
Visualizes executive marketplace performance metrics derived from PostgreSQL
star-schema views and pre-aggregated fact tables.
Enforces strict grain discipline to prevent join fan-out and double-counting.
Uses Decimal-safe formatting throughout.
"""

from decimal import Decimal
from typing import Optional
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from commercelens.app.components import (
    apply_plotly_theme,
    format_currency_decimal,
    format_freight_subtitle,
    format_percentage_safe,
    metric_card,
)
from commercelens.app.data import (
    get_category_performance,
    get_executive_kpis,
    get_monthly_sales_trend,
    get_order_status_distribution,
    get_state_sales_distribution,
)


def render_executive_tab(selected_state: Optional[str] = "All") -> None:
    """Renders Tab 1: Executive Analytics Dashboard."""
    st.markdown("### 📊 Executive Business Analytics")
    st.markdown(
        "Marketplace financial performance, SLA fulfillment, and geographic dynamics. "
        "All figures reflect verified PostgreSQL star-schema metrics consistent with the Power BI semantic model."
    )

    try:
        kpis = get_executive_kpis(selected_state=selected_state)
    except Exception as e:
        st.error(f"❌ Failed to query executive KPIs from PostgreSQL: {e}")
        st.info("Ensure PostgreSQL is running on localhost:5432 with commercelens_db initialized.")
        return

    # 1. Primary Financial & Order Volume KPIs
    st.markdown("#### Core Financial & Operational KPIs")
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        gmv_fmt = format_currency_decimal(kpis.get("total_gmv"), allow_millions=True)
        metric_card(
            title="Delivered GMV",
            value=gmv_fmt,
            subtitle="Delivered item merchandise value",
            delta="100% of validated sales",
        )
    with c2:
        tot_orders = kpis.get("total_orders") or 0
        del_orders = kpis.get("delivered_orders") or 0
        del_pct = (del_orders / tot_orders * 100.0) if tot_orders > 0 else 0.0
        metric_card(
            title="Delivered Orders",
            value=f"{del_orders:,}",
            subtitle=f"{del_pct:.1f}% of total placed orders",
        )
    with c3:
        aov_fmt = format_currency_decimal(kpis.get("aov"), allow_millions=False)
        metric_card(
            title="Average Order Value",
            value=aov_fmt,
            subtitle="GMV / delivered orders",
        )
    with c4:
        metric_card(
            title="Freight-to-Merchandise",
            value=format_percentage_safe(kpis.get("freight_ratio_pct")),
            subtitle=format_freight_subtitle(kpis.get("total_freight")),
        )

    # 2. Operational Fulfillment & Attrition KPIs
    c5, c6, c7, c8 = st.columns(4)
    with c5:
        metric_card(
            title="On-Time Delivery Rate",
            value=format_percentage_safe(kpis.get("on_time_rate_pct")),
            subtitle=f"{kpis.get('on_time_orders', 0):,} on-time orders",
            delta="SLA eligible: 96,470 orders",
        )
    with c6:
        metric_card(
            title="Late Delivery Rate",
            value=format_percentage_safe(kpis.get("late_rate_pct")),
            subtitle=f"{kpis.get('late_orders', 0):,} late arrivals",
            delta="Breached delivery SLA",
            delta_color="inverse",
        )
    with c7:
        metric_card(
            title="Cancellation Rate",
            value=format_percentage_safe(kpis.get("canceled_rate_pct")),
            subtitle=f"{kpis.get('canceled_orders', 0):,} canceled orders",
            delta_color="inverse",
        )
    with c8:
        metric_card(
            title="Unavailable Rate",
            value=format_percentage_safe(kpis.get("unavailable_rate_pct")),
            subtitle=f"{kpis.get('unavailable_orders', 0):,} unfulfilled listings",
            delta_color="inverse",
        )

    st.markdown("---")

    # 3. Monthly Sales Trends
    st.markdown("#### Monthly Sales Performance & Order Volume (2016 – 2018)")
    try:
        monthly_df = get_monthly_sales_trend()
        if not monthly_df.empty:
            monthly_plot_df = monthly_df.copy()
            # Omit trailing post-operational periods that contain no delivered orders
            # (Olist dataset collection ended in August 2018; Sept/Oct 2018 contain 0 delivered orders)
            monthly_plot_df = monthly_plot_df[monthly_plot_df["delivered_orders_count"] > 0]
            monthly_plot_df["gmv_float"] = monthly_plot_df["gmv"].astype(float)
            monthly_plot_df["orders_int"] = monthly_plot_df["delivered_orders_count"].astype(int)

            fig_monthly = go.Figure()
            # GMV Bars
            fig_monthly.add_trace(
                go.Bar(
                    x=monthly_plot_df["month_year"],
                    y=monthly_plot_df["gmv_float"],
                    name="Delivered GMV (R$)",
                    marker_color="#2b5c8f",
                    opacity=0.85,
                    yaxis="y1",
                )
            )
            # Order Volume Line
            fig_monthly.add_trace(
                go.Scatter(
                    x=monthly_plot_df["month_year"],
                    y=monthly_plot_df["orders_int"],
                    name="Delivered Orders",
                    mode="lines+markers",
                    line=dict(color="#e27c3e", width=2.5),
                    marker=dict(size=6),
                    yaxis="y2",
                )
            )
            fig_monthly.update_layout(
                yaxis=dict(title="Delivered GMV (R$)", tickprefix="R$ ", showgrid=True),
                yaxis2=dict(title="Delivered Orders", overlaying="y", side="right", showgrid=False),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                hovermode="x unified",
            )
            apply_plotly_theme(fig_monthly, height=360)
            st.plotly_chart(fig_monthly, use_container_width=True)
            st.caption(
                "Note: Operational marketplace snapshot concluded in August 2018. "
                "Trailing post-snapshot records (Sept–Oct 2018 with 0 delivered orders) are excluded from the trend line."
            )
        else:
            st.info("No monthly trend data returned from v_monthly_sales_performance.")
    except Exception as e:
        st.warning(f"Unable to render monthly trends: {e}")

    # 4. Product Categories and Geographic Distribution
    col_cat, col_geo = st.columns([1, 1])

    with col_cat:
        st.markdown("#### Top 10 Product Categories by GMV")
        try:
            cat_df = get_category_performance(limit=10)
            if not cat_df.empty:
                cat_plot_df = cat_df.copy()
                cat_plot_df["gmv_float"] = cat_plot_df["gmv"].astype(float)
                max_gmv = float(cat_plot_df["gmv_float"].max())
                fig_cat = px.bar(
                    cat_plot_df,
                    x="gmv_float",
                    y="category_name",
                    orientation="h",
                    text=cat_plot_df["gmv"].apply(lambda v: format_currency_decimal(v, allow_millions=True)),
                    color="gmv_float",
                    color_continuous_scale="Blues",
                    labels={"gmv_float": "Delivered GMV (R$)", "category_name": "Product Category"},
                )
                fig_cat.update_layout(
                    yaxis=dict(autorange="reversed", title=""),
                    xaxis=dict(range=[0, max_gmv * 1.25], title="Delivered GMV (R$)", tickprefix="R$ "),
                    margin=dict(l=20, r=60, t=25, b=35),
                    coloraxis_showscale=False,
                )
                fig_cat.update_traces(
                    textposition="outside",
                    cliponaxis=False,
                    hovertemplate="<b>%{y}</b><br>Delivered GMV: R$ %{x:,.2f}<extra></extra>",
                )
                apply_plotly_theme(fig_cat, height=380)
                st.plotly_chart(fig_cat, use_container_width=True)
            else:
                st.info("No category data returned.")
        except Exception as e:
            st.warning(f"Unable to render category rankings: {e}")

    with col_geo:
        st.markdown("#### Top 10 Customer States by Delivered GMV")
        try:
            state_df = get_state_sales_distribution(limit=10)
            if not state_df.empty:
                state_plot_df = state_df.copy()
                state_plot_df["delivered_gmv_float"] = state_plot_df["delivered_gmv"].astype(float)
                max_state_gmv = float(state_plot_df["delivered_gmv_float"].max())
                fig_state = px.bar(
                    state_plot_df,
                    x="customer_state",
                    y="delivered_gmv_float",
                    text=state_plot_df["delivered_gmv"].apply(lambda v: format_currency_decimal(v, allow_millions=True)),
                    color="delivered_gmv_float",
                    color_continuous_scale="Teal",
                    labels={"delivered_gmv_float": "Delivered GMV (R$)", "customer_state": "State"},
                )
                fig_state.update_traces(
                    textposition="outside",
                    cliponaxis=False,
                    hovertemplate="<b>State: %{x}</b><br>Delivered GMV: R$ %{y:,.2f}<extra></extra>",
                )
                fig_state.update_layout(
                    yaxis=dict(range=[0, max_state_gmv * 1.15]),
                    margin=dict(l=40, r=20, t=25, b=35),
                    coloraxis_showscale=False,
                )
                apply_plotly_theme(fig_state, height=380)
                st.plotly_chart(fig_state, use_container_width=True)
            else:
                st.info("No regional distribution data returned.")
        except Exception as e:
            st.warning(f"Unable to render regional distribution: {e}")

    # 5. Order Status Distribution Table
    st.markdown("#### Order Lifecycle & Status Distribution")
    try:
        status_df = get_order_status_distribution()
        st.dataframe(
            status_df.rename(
                columns={
                    "order_status": "Order Status",
                    "order_count": "Distinct Orders",
                    "percentage": "Share of Total (%)",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
    except Exception as e:
        st.warning(f"Unable to load status distribution: {e}")
