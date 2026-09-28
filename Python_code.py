import os
import sqlite3
import pandas as pd

def main():
    # -------------------------------------------------------------
    # 1. Directory and File Paths Setup
    # -------------------------------------------------------------
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Locate raw_data Excel file (case-insensitive check)
    excel_filename = None
    for candidate in ["raw_data.xlsx", "Raw_data.xlsx", "raw_data.xls", "Raw_data.xls"]:
        full_candidate_path = os.path.join(base_dir, candidate)
        if os.path.exists(full_candidate_path):
            excel_filename = candidate
            break
            
    if not excel_filename:
        # Fallback search for any file starting with raw_data
        for file in os.listdir(base_dir):
            if file.lower().startswith("raw_data") and (file.endswith(".xlsx") or file.endswith(".xls")):
                excel_filename = file
                break

    if not excel_filename:
        raise FileNotFoundError(f"No excel file named 'raw_data' found in {base_dir}")

    excel_path = os.path.join(base_dir, excel_filename)
    db_path = os.path.join(base_dir, "sales_database.db")
    output_excel_path = os.path.join(base_dir, "sales_analysis_results.xlsx")

    print(f"[1/4] Reading Excel file from: {excel_path}")
    df = pd.read_excel(excel_path)
    print(f"      Loaded {len(df):,} rows and {len(df.columns)} columns.")

    # -------------------------------------------------------------
    # 2. Data Cleaning & Column Standardization for SQL
    # -------------------------------------------------------------
    # Standardize column names to lowercase with underscores (e.g. 'Sub-Category' -> 'sub_category')
    df.columns = (
        df.columns.str.strip()
        .str.lower()
        .str.replace(" ", "_")
        .str.replace("-", "_")
    )

    # Standardize order_date to YYYY-MM-DD string for reliable SQLite date functions
    if "order_date" in df.columns:
        df["order_date"] = pd.to_datetime(df["order_date"], format="mixed").dt.strftime("%Y-%m-%d")

    # -------------------------------------------------------------
    # 3. Create SQLite Database and Store in 'Sales' Table
    # -------------------------------------------------------------
    print(f"[2/4] Connecting to SQLite database at: {db_path}")
    conn = sqlite3.connect(db_path)

    print("      Writing data to 'Sales' table...")
    df.to_sql(
        name="Sales",
        con=conn,
        if_exists="replace",  # Replaces existing table if script is re-run
        index=False,
        chunksize=1000
    )
    print("      Successfully stored data in 'Sales' table.")

    # Create index on common query dimensions for fast querying
    cursor = conn.cursor()
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_category ON Sales(category);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_sub_cat ON Sales(sub_category);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_order_date ON Sales(order_date);")
    conn.commit()

    # -------------------------------------------------------------
    # 4. Define SQL Queries
    # -------------------------------------------------------------
    print("[3/4] Defining analytical SQL queries...")
    
    # Query 1: Category Revenue
    query_category_revenue = """
    SELECT 
        category,
        COUNT(*) AS total_items_sold,
        COUNT(DISTINCT order_id) AS total_orders,
        ROUND(SUM(sales), 2) AS total_revenue,
        ROUND(SUM(sales) * 100.0 / SUM(SUM(sales)) OVER(), 2) AS pct_of_total_revenue
    FROM Sales
    GROUP BY category
    ORDER BY total_revenue DESC;
    """

    # Query 2: Category Stats
    query_category_stats = """
    SELECT 
        category,
        COUNT(*) AS total_transactions,
        ROUND(SUM(sales), 2) AS total_sales,
        ROUND(AVG(sales), 2) AS avg_sales,
        ROUND(MIN(sales), 2) AS min_sales,
        ROUND(MAX(sales), 2) AS max_sales
    FROM Sales
    GROUP BY category
    ORDER BY avg_sales DESC;
    """

    # Query 3: Top 3 Sales in Each Category
    query_top_3_sales = """
    WITH RankedSales AS (
        SELECT 
            order_id,
            category,
            sub_category,
            product_name,
            ROUND(sales, 2) AS sales,
            DENSE_RANK() OVER (
                PARTITION BY category 
                ORDER BY sales DESC
            ) AS rank_in_category
        FROM Sales
    )
    SELECT 
        rank_in_category,
        category,
        sub_category,
        sales,
        product_name,
        order_id
    FROM RankedSales
    WHERE rank_in_category <= 3
    ORDER BY category, rank_in_category, sales DESC;
    """

    # Query 4: Month-over-Month (MoM) Growth
    query_mom_growth = """
    WITH MonthlySales AS (
        SELECT 
            strftime('%Y-%m', order_date) AS year_month,
            ROUND(SUM(sales), 2) AS monthly_sales
        FROM Sales
        WHERE order_date IS NOT NULL
        GROUP BY year_month
    )
    SELECT 
        year_month,
        monthly_sales,
        LAG(monthly_sales) OVER (ORDER BY year_month) AS prev_month_sales,
        ROUND(monthly_sales - LAG(monthly_sales) OVER (ORDER BY year_month), 2) AS mom_sales_change,
        ROUND(
            (monthly_sales - LAG(monthly_sales) OVER (ORDER BY year_month)) * 100.0 / 
            LAG(monthly_sales) OVER (ORDER BY year_month), 
            2
        ) AS mom_growth_pct
    FROM MonthlySales
    ORDER BY year_month;
    """

    # Query 5: Underperforming Subcategories
    query_underperforming_subcategories = """
    WITH SubCategoryMetrics AS (
        SELECT 
            category,
            sub_category,
            COUNT(*) AS total_items_sold,
            COUNT(DISTINCT order_id) AS total_orders,
            ROUND(SUM(sales), 2) AS total_sales,
            ROUND(AVG(sales), 2) AS avg_sale_per_item,
            ROUND(SUM(sales) * 100.0 / SUM(SUM(sales)) OVER(), 2) AS pct_of_company_revenue,
            ROUND(AVG(SUM(sales)) OVER(), 2) AS avg_subcategory_benchmark
        FROM Sales
        GROUP BY category, sub_category
    )
    SELECT 
        category,
        sub_category,
        total_items_sold,
        total_orders,
        total_sales,
        avg_sale_per_item,
        pct_of_company_revenue,
        avg_subcategory_benchmark,
        CASE 
            WHEN total_sales < avg_subcategory_benchmark THEN 'Underperforming (< Benchmark)'
            ELSE 'Above Benchmark'
        END AS performance_status
    FROM SubCategoryMetrics
    ORDER BY total_sales ASC;
    """

    # Query 6: Category Benchmarks
    query_category_benchmarks = """
    WITH CategoryMetrics AS (
        SELECT 
            category,
            COUNT(*) AS total_items_sold,
            COUNT(DISTINCT order_id) AS total_orders,
            ROUND(SUM(sales), 2) AS total_sales,
            ROUND(AVG(sales), 2) AS avg_sales_per_item,
            ROUND(SUM(sales) * 100.0 / SUM(SUM(sales)) OVER(), 2) AS pct_revenue,
            ROUND(AVG(SUM(sales)) OVER(), 2) AS avg_category_benchmark
        FROM Sales
        GROUP BY category
    )
    SELECT 
        category,
        total_items_sold,
        total_orders,
        total_sales,
        avg_sales_per_item,
        pct_revenue,
        avg_category_benchmark,
        CASE 
            WHEN total_sales >= avg_category_benchmark THEN 'Top Performing Category'
            ELSE 'Below Category Average'
        END AS performance_benchmark_status
    FROM CategoryMetrics
    ORDER BY total_sales DESC;
    """

    # Dictionary mapping Sheet Name -> SQL Query
    query_sheets = {
        "Category Revenue": query_category_revenue,
        "Category Stats": query_category_stats,
        "Top 3 Sales in Category": query_top_3_sales,
        "MoM Growth": query_mom_growth,
        "Underperforming Subcategories": query_underperforming_subcategories,
        "Category Benchmarks": query_category_benchmarks
    }

    # -------------------------------------------------------------
    # 5. Extract Results into One Excel File with Multiple Sheets
    # -------------------------------------------------------------
    print(f"[4/4] Executing queries and exporting to multi-sheet Excel file: {output_excel_path}")
    with pd.ExcelWriter(output_excel_path, engine="openpyxl") as writer:
        for sheet_name, sql in query_sheets.items():
            result_df = pd.read_sql_query(sql, conn)
            result_df.to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"      Sheet '{sheet_name}': {len(result_df)} rows exported.")

    # Close connection
    conn.close()

    print("=" * 60)
    print("SUCCESS: Process completed successfully!")
    print(f"- SQLite Database created: {db_path}")
    print(f"- Multi-sheet Excel exported: {output_excel_path}")
    print("=" * 60)

if __name__ == "__main__":
    main()
