#!/usr/bin/env python3
"""
Streamlit Admin Console for One-Pager Report Management
Deployed version for Streamlit Cloud with secrets management
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import asyncio
import sys
import os
from typing import List, Dict, Any
import json

# Add the app directory to the Python path to access the app services
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

# Load environment variables from .env file first, then from Streamlit secrets
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

# Set environment variables from Streamlit secrets (overrides .env if present)
try:
    if 'supabase' in st.secrets:
        os.environ['SUPABASE_URL'] = st.secrets['supabase']['url']
        os.environ['SUPABASE_ANON_KEY'] = st.secrets['supabase']['key']
        st.success("✅ Using Supabase credentials from Streamlit secrets")
    elif os.getenv('SUPABASE_URL') and os.getenv('SUPABASE_ANON_KEY'):
        st.success("✅ Using Supabase credentials from .env file")
    else:
        st.warning("⚠️ Supabase credentials not found in secrets or .env. App will run in demo mode.")
except Exception as e:
    st.warning(f"⚠️ Error loading secrets: {str(e)}. App will run in demo mode.")

from app.database_service import DatabaseService, OnePagerRecord
from app.request_manager import request_manager

# Page configuration
st.set_page_config(
    page_title="One-Pager Admin Console",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
    .status-success { color: #28a745; font-weight: bold; }
    .status-error { color: #dc3545; font-weight: bold; }
    .status-in-progress { color: #ffc107; font-weight: bold; }
    .status-partial-success { color: #fd7e14; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

class AdminConsole:
    def __init__(self):
        self.db_service = None
        self.initialize_database()

    def initialize_database(self):
        """Initialize database connection using environment variables or Streamlit secrets"""
        try:
            # Environment variables should already be set from the main initialization
            # Just verify they exist
            if not os.getenv('SUPABASE_URL') or not os.getenv('SUPABASE_ANON_KEY'):
                raise ValueError("Supabase credentials not found in environment variables")

            self.db_service = DatabaseService()
            st.success("✅ Database connected successfully")
        except Exception as e:
            st.warning(f"⚠️ Database connection failed: {str(e)}")
            st.info("App will run in demo mode with sample data")
            self.db_service = None

    def get_recent_records(self, limit: int = 100) -> List[OnePagerRecord]:
        """Get recent records from database"""
        if self.db_service is None:
            return []
        try:
            records = asyncio.run(self.db_service.get_recent_one_pager_records(limit))
            return records or []
        except Exception as e:
            print(f"Database error: {str(e)}")
            st.warning(f"Database connection error: {str(e)}")
            st.info("App will show sample data instead")
            return []

    def get_records_by_company(self, company_name: str) -> List[OnePagerRecord]:
        """Get records for specific company"""
        try:
            return asyncio.run(self.db_service.get_one_pager_records_by_company(company_name))
        except Exception as e:
            st.error(f"Error fetching company records: {str(e)}")
            return []

    def get_records_by_status(self, status: str) -> List[OnePagerRecord]:
        """Get records by status"""
        try:
            records = asyncio.run(self.db_service.get_recent_one_pager_records(1000))
            return [r for r in records if r.status == status]
        except Exception as e:
            st.error(f"Error fetching records by status: {str(e)}")
            return []

    def delete_record(self, record_id: int) -> bool:
        """Delete a record"""
        try:
            return asyncio.run(self.db_service.delete_one_pager_record(record_id))
        except Exception as e:
            st.error(f"Error deleting record: {str(e)}")
            return False


def render_header():
    """Render the main header"""
    st.markdown('<h1 class="main-header">📊 One-Pager Admin Console</h1>', unsafe_allow_html=True)
    st.markdown("---")

def render_sidebar(console: AdminConsole):
    """Render sidebar with filters and controls"""
    st.sidebar.header("🔧 Controls")

    # Refresh button
    if st.sidebar.button("🔄 Refresh Data", type="primary"):
        st.rerun()

    # Filters
    st.sidebar.subheader("📋 Filters")

    # Status filter
    status_options = ["All", "in-progress", "success", "partial-success", "error", "timeout"]
    selected_status = st.sidebar.selectbox("Status", status_options)

    # Company filter
    records = console.get_recent_records(1000)
    companies = ["All"] + sorted(list(set([r.company_name for r in records])))
    selected_company = st.sidebar.selectbox("Company", companies)

    # Date range filter
    st.sidebar.subheader("📅 Date Range")
    days_back = st.sidebar.slider("Days back", 1, 30, 7)
    from datetime import timezone
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)

    return {
        "status": selected_status,
        "company": selected_company,
        "days_back": days_back,
        "cutoff_date": cutoff_date
    }

def render_metrics(records: List[OnePagerRecord]):
    """Render key metrics"""
    st.subheader("📈 Key Metrics")

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        total_records = len(records)
        st.metric("Total Requests", total_records)

    with col2:
        success_count = len([r for r in records if r.status == "success"])
        success_rate = (success_count / total_records * 100) if total_records > 0 else 0
        st.metric("Success Rate", f"{success_rate:.1f}%")

    with col3:
        in_progress_count = len([r for r in records if r.status == "in-progress"])
        st.metric("In Progress", in_progress_count)

    with col4:
        error_count = len([r for r in records if r.status == "error"])
        st.metric("Errors", error_count)

    with col5:
        timeout_count = len([r for r in records if r.status == "timeout"])
        st.metric("Timeouts", timeout_count)

    # Additional metrics
    if records:
        st.subheader("📊 Data Summary")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            pptx_count = len([r for r in records if r.pptx_blob_url])
            st.metric("PPTX Files", f"{pptx_count}/{total_records}")

        with col2:
            excel_count = len([r for r in records if r.excel_provided])
            st.metric("Excel Files", f"{excel_count}/{total_records}")

        with col3:
            azure_success = len([r for r in records if r.azure_upload_ok])
            st.metric("Azure Uploads", f"{azure_success}/{total_records}")

        with col4:
            error_records = len([r for r in records if r.error_message])
            st.metric("With Errors", f"{error_records}/{total_records}")

        # Add average duration as a separate row
        st.subheader("⏱️ Performance Metrics")
        col_perf1, col_perf2, col_perf3 = st.columns(3)

        with col_perf1:
            avg_duration = sum([r.duration_ms for r in records if r.duration_ms > 0]) / len([r for r in records if r.duration_ms > 0]) if any(r.duration_ms > 0 for r in records) else 0
            st.metric("Avg Duration", f"{avg_duration/1000:.1f}s")

        with col_perf2:
            max_duration = max([r.duration_ms for r in records if r.duration_ms > 0], default=0)
            st.metric("Max Duration", f"{max_duration/1000:.1f}s")

        with col_perf3:
            timeout_rate = (timeout_count / total_records * 100) if total_records > 0 else 0
            st.metric("Timeout Rate", f"{timeout_rate:.1f}%")

def render_charts(records: List[OnePagerRecord], filters: Dict):
    """Render charts and visualizations"""
    st.subheader("📊 Analytics")

    col1, col2 = st.columns(2)

    with col1:
        # Status distribution pie chart
        status_counts = {}
        for record in records:
            status_counts[record.status] = status_counts.get(record.status, 0) + 1

        if status_counts:
            fig_pie = px.pie(
                values=list(status_counts.values()),
                names=list(status_counts.keys()),
                title="Request Status Distribution",
                color_discrete_map={
                    "success": "#28a745",
                    "error": "#dc3545",
                    "in-progress": "#ffc107",
                    "partial-success": "#fd7e14",
                    "timeout": "#6f42c1"
                }
            )
            st.plotly_chart(fig_pie, use_container_width=True)

    with col2:
        # Company activity bar chart
        if records:
            company_counts = {}
            for r in records:
                # Clean company name to avoid duplicates
                company_name = r.company_name.strip()
                company_counts[company_name] = company_counts.get(company_name, 0) + 1

            if company_counts:
                # Get top 5 companies
                top_companies = sorted(company_counts.items(), key=lambda x: x[1], reverse=True)[:5]

                company_df = pd.DataFrame(top_companies, columns=['Company', 'Requests'])
                fig_companies = px.bar(
                    company_df,
                    x='Company',
                    y='Requests',
                    title="Top 5 Most Active Companies",
                    color='Requests',
                    color_continuous_scale='Blues'
                )
                fig_companies.update_layout(
                    xaxis_title="Company Name",
                    yaxis_title="Number of Requests",
                    showlegend=False,
                    coloraxis_showscale=False  # Remove the color scale legend
                )
                st.plotly_chart(fig_companies, use_container_width=True)
            else:
                st.info("No company data available")
        else:
            st.info("No records available for charting")

def render_requests_table(records: List[OnePagerRecord], console: AdminConsole):
    """Render the main requests table"""
    st.subheader("📋 Request Details")

    if not records:
        st.info("No records found matching the current filters.")
        return

    # Prepare data for table
    table_data = []
    for record in records:
        # Format PPTX URL for display - show complete URL
        pptx_display = "❌" if not record.pptx_blob_url else record.pptx_blob_url

        # Format Excel info
        excel_display = "❌" if not record.excel_provided else (record.excel_filename or "Yes")

        # Format Excel blob URL for display
        excel_blob_display = "❌" if not record.excel_blob_url else record.excel_blob_url

        # Format error message
        error_display = ""
        if record.error_message:
            if len(record.error_message) > 50:
                error_display = f"{record.error_message[:47]}..."
            else:
                error_display = record.error_message

        # Format sections data
        sections_status = record.sections_status if record.sections_status else {}
        sections_response = record.sections_response if record.sections_response else {}
        section_sources = record.section_sources if record.section_sources else {}
        product_images = record.product_images if record.product_images else {}
        products = record.products if record.products else {}

        # Format JSON data for display
        def format_json_data(data, max_length=100):
            if not data:
                return "N/A"
            data_str = str(data)
            if len(data_str) > max_length:
                return f"{data_str[:max_length]}..."
            return data_str

        table_data.append({
            "ID": record.id,
            "Request ID": record.request_id,
            "Company": record.company_name,
            "Website": record.website_url,
            "Status": record.status,
            "Duration (s)": f"{record.duration_ms/1000:.1f}" if record.duration_ms > 0 else "N/A",
            "Created": pd.to_datetime(record.created_at).tz_localize(None).strftime("%Y-%m-%d %H:%M:%S") if pd.to_datetime(record.created_at).tz else pd.to_datetime(record.created_at).strftime("%Y-%m-%d %H:%M:%S"),
            "Updated": pd.to_datetime(record.updated_at).tz_localize(None).strftime("%Y-%m-%d %H:%M:%S") if pd.to_datetime(record.updated_at).tz else pd.to_datetime(record.updated_at).strftime("%Y-%m-%d %H:%M:%S"),
            "PPTX URL": pptx_display,
            "PPTX Filename": record.pptx_filename or "N/A",
            "PPTX Path": record.pptx_blob_path or "N/A",
            "Metadata URL": record.metadata_blob_url or "N/A",
            "Excel": excel_display,
            "Excel Filename": record.excel_filename or "N/A",
            "Excel Size": f"{record.excel_size} bytes" if record.excel_size else "N/A",
            "Excel Blob URL": excel_blob_display,
            "Excel Blob Path": record.excel_blob_path or "N/A",
            "Azure Upload": "Success" if record.azure_upload_ok else "Failed",
            "Azure Error": record.azure_upload_error or "N/A",
            "Container": record.container or "N/A",
            "Folder Title": record.folder_title or "N/A",
            "Base Path": record.base_path or "N/A",
            "Company Logo": record.company_logo or "N/A",
            "Error Type": record.error_type or "N/A",
            "Error Message": error_display,
            "Warnings": format_json_data(record.warnings, 50),
            "Sections Status": format_json_data(sections_status, 50),
            "Sections Response": format_json_data(sections_response, 50),
            "Section Sources": format_json_data(section_sources, 50),
            "Product Images": format_json_data(product_images, 50),
            "Products": format_json_data(products, 50)
        })

    df = pd.DataFrame(table_data)

    # Display table with pagination
    page_size = 20
    total_pages = len(df) // page_size + (1 if len(df) % page_size > 0 else 0)

    if total_pages > 1:
        page = st.selectbox("Page", range(1, total_pages + 1))
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        display_df = df.iloc[start_idx:end_idx]
    else:
        display_df = df

    # Add status styling to the display DataFrame
    def style_status(val):
        if val == "success":
            return "color: #28a745; font-weight: bold"
        elif val == "error":
            return "color: #dc3545; font-weight: bold"
        elif val == "in-progress":
            return "color: #ffc107; font-weight: bold"
        elif val == "partial-success":
            return "color: #fd7e14; font-weight: bold"
        return ""

    styled_display_df = display_df.style.applymap(style_status, subset=['Status'])

    st.dataframe(styled_display_df, use_container_width=True)

    # Show clickable links for PPTX and Excel URLs
    st.subheader("🔗 Direct Links")
    for i, record in enumerate(records[:10]):  # Show first 10 records
        if record.pptx_blob_url:
            st.markdown(f"**{record.company_name}**: [Download PPTX]({record.pptx_blob_url})")
        if record.excel_blob_url:
            st.markdown(f"**{record.company_name}**: [Download Excel]({record.excel_blob_url})")
        if record.metadata_blob_url:
            st.markdown(f"**{record.company_name}**: [View Metadata]({record.metadata_blob_url})")

    # Action buttons
    st.subheader("🔧 Actions")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📊 Export Data"):
            csv = df.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"one_pager_requests_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )

    with col2:
        if st.button("🔄 Refresh"):
            st.rerun()

def render_request_details(records: List[OnePagerRecord]):
    """Render detailed view for selected request"""
    st.subheader("🔍 Request Details")

    if not records:
        st.info("No records available for detailed view.")
        return

    # Request selector
    request_options = [f"{r.request_id} - {r.company_name} ({r.status})" for r in records]
    selected_idx = st.selectbox("Select Request", range(len(request_options)), format_func=lambda x: request_options[x])

    if selected_idx is not None:
        selected_record = records[selected_idx]

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Basic Information**")
            st.write(f"**Request ID:** {selected_record.request_id}")
            st.write(f"**Company:** {selected_record.company_name}")
            st.write(f"**Website:** {selected_record.website_url}")
            st.write(f"**Status:** {selected_record.status}")
            st.write(f"**Duration:** {selected_record.duration_ms/1000:.1f}s" if selected_record.duration_ms > 0 else "N/A")
            created_dt = pd.to_datetime(selected_record.created_at)
            updated_dt = pd.to_datetime(selected_record.updated_at)
            created_str = created_dt.tz_localize(None).strftime('%Y-%m-%d %H:%M:%S') if created_dt.tz else created_dt.strftime('%Y-%m-%d %H:%M:%S')
            updated_str = updated_dt.tz_localize(None).strftime('%Y-%m-%d %H:%M:%S') if updated_dt.tz else updated_dt.strftime('%Y-%m-%d %H:%M:%S')
            st.write(f"**Created:** {created_str}")
            st.write(f"**Updated:** {updated_str}")

        with col2:
            st.markdown("**File Information**")
            st.write(f"**PPTX Filename:** {selected_record.pptx_filename or 'N/A'}")
            st.write(f"**PPTX URL:** {selected_record.pptx_blob_url or 'N/A'}")
            st.write(f"**PPTX Path:** {selected_record.pptx_blob_path or 'N/A'}")
            st.write(f"**Metadata URL:** {selected_record.metadata_blob_url or 'N/A'}")
            st.write(f"**Excel Provided:** {'Yes' if selected_record.excel_provided else 'No'}")
            st.write(f"**Excel Filename:** {selected_record.excel_filename or 'N/A'}")
            st.write(f"**Excel Size:** {f'{selected_record.excel_size} bytes' if selected_record.excel_size else 'N/A'}")
            st.write(f"**Excel Blob URL:** {selected_record.excel_blob_url or 'N/A'}")
            st.write(f"**Excel Blob Path:** {selected_record.excel_blob_path or 'N/A'}")
            st.write(f"**Azure Upload:** {'Success' if selected_record.azure_upload_ok else 'Failed'}")
            st.write(f"**Azure Error:** {selected_record.azure_upload_error or 'N/A'}")
            st.write(f"**Container:** {selected_record.container or 'N/A'}")
            st.write(f"**Folder Title:** {selected_record.folder_title or 'N/A'}")
            st.write(f"**Base Path:** {selected_record.base_path or 'N/A'}")
            st.write(f"**Company Logo:** {selected_record.company_logo or 'N/A'}")

        # Error information
        if selected_record.error_message:
            st.markdown("**Error Information**")
            st.error(f"**Error Type:** {selected_record.error_type}")
            st.error(f"**Error Message:** {selected_record.error_message}")

        # Warnings
        if selected_record.warnings:
            st.markdown("**Warnings**")
            for warning in selected_record.warnings:
                st.warning(warning)

        # Sections and Data
        st.markdown("**Sections and Generated Data**")

        col1, col2 = st.columns(2)

        with col1:
            if selected_record.sections_status:
                st.markdown("**Sections Status**")
                st.json(selected_record.sections_status)

            if selected_record.sections_response:
                st.markdown("**Sections Response**")
                st.json(selected_record.sections_response)

        with col2:
            if selected_record.section_sources:
                st.markdown("**Section Sources**")
                st.json(selected_record.section_sources)

            if selected_record.product_images:
                st.markdown("**Product Images**")
                st.json(selected_record.product_images)

        if selected_record.products:
            st.markdown("**Products**")
            st.json(selected_record.products)

        # Raw JSON data
        if st.checkbox("Show Complete Raw JSON Data"):
            st.json(selected_record.model_dump())

def main():
    """Main function to run the admin console"""
    console = AdminConsole()

    # Render header
    render_header()

    # Render sidebar and get filters
    filters = render_sidebar(console)

    # Get filtered records
    all_records = console.get_recent_records(1000)

    # If no records, show sample data for testing
    if not all_records:
        st.warning("⚠️ No records found in database. This might be due to:")
        st.write("- Database connection issues")
        st.write("- No data has been generated yet")
        st.write("- Network connectivity problems")

        # Create sample data for demonstration
        from datetime import datetime, timedelta
        import random

        st.info("📊 Showing sample data for demonstration...")
        sample_records = []

        # Create data across multiple days for better chart visualization
        for i in range(20):
            # Create records across the last 7 days
            days_ago = random.randint(0, 6)
            hours_ago = random.randint(0, 23)
            created_time = datetime.now() - timedelta(days=days_ago, hours=hours_ago)

            sample_records.append(OnePagerRecord(
                id=i+1,
                request_id=f"sample_{i+1}",
                company_name=f"Sample Company {i+1}",
                website_url=f"https://example{i+1}.com",
                status=random.choice(["success", "in-progress", "error", "partial-success"]),
                generated_at=created_time,
                duration_ms=random.randint(5000, 30000),
                folder_title=f"sample_{i+1}",
                base_path=f"one-pagers/sample_{i+1}",
                container="bynd-dev",
                pptx_filename=f"sample_{i+1}.pptx",
                pptx_blob_url=f"https://example.com/sample_{i+1}.pptx" if random.choice([True, False]) else None,
                pptx_blob_path=f"one-pagers/sample_{i+1}/sample_{i+1}.pptx",
                metadata_blob_url=f"https://example.com/sample_{i+1}_metadata.json" if random.choice([True, False]) else None,
                excel_provided=random.choice([True, False]),
                excel_filename=f"sample_{i+1}.xlsx" if random.choice([True, False]) else None,
                excel_size=random.randint(10000, 100000) if random.choice([True, False]) else None,
                excel_blob_url=f"https://example.com/sample_{i+1}.xlsx" if random.choice([True, False]) else None,
                excel_blob_path=f"one-pagers/sample_{i+1}/excel/sample_{i+1}.xlsx" if random.choice([True, False]) else None,
                sections_status={"about": {"ok": True}, "operations": {"ok": False}} if random.choice([True, False]) else None,
                sections_response={"about": "Sample response"} if random.choice([True, False]) else None,
                section_sources={"about": ["https://example.com"]} if random.choice([True, False]) else None,
                product_images=[{"url": "https://example.com/image.jpg"}] if random.choice([True, False]) else None,
                products=[{"name": "Sample Product"}] if random.choice([True, False]) else None,
                company_logo="https://example.com/logo.png" if random.choice([True, False]) else None,
                azure_upload_ok=random.choice([True, False]),
                azure_upload_error="Sample error" if random.choice([True, False]) else None,
                warnings=["Sample warning"] if random.choice([True, False]) else None,
                error_type="Sample error" if random.choice([True, False]) else None,
                error_message="Sample error message" if random.choice([True, False]) else None,
                created_at=created_time,
                updated_at=created_time + timedelta(minutes=random.randint(1, 60))
            ))
        all_records = sample_records

    # Apply filters
    filtered_records = all_records

    if filters["status"] != "All":
        filtered_records = [r for r in filtered_records if r.status == filters["status"]]

    if filters["company"] != "All":
        filtered_records = [r for r in filtered_records if r.company_name == filters["company"]]

    # Filter by date (handle timezone-aware comparison)
    from datetime import timezone
    cutoff_date_aware = filters["cutoff_date"].replace(tzinfo=timezone.utc) if filters["cutoff_date"].tzinfo is None else filters["cutoff_date"]
    filtered_records = [r for r in filtered_records if pd.to_datetime(r.created_at) >= cutoff_date_aware]

    # Render metrics
    render_metrics(filtered_records)

    # Render charts
    render_charts(filtered_records, filters)

    # Tabs for different views
    tab1, tab2 = st.tabs(["📋 Requests Table", "🔍 Request Details"])

    with tab1:
        render_requests_table(filtered_records, console)

    with tab2:
        render_request_details(filtered_records)

if __name__ == "__main__":
    main()
