-- =============================================================
-- Super Store Sales Analysis - SQL Queries
-- Database : SQLite (database/sales_database.db), table: Sales
--
-- Each query starts with a "-- name: <Sheet Name>" marker.
-- The name becomes the sheet name in sales_analysis_results.xlsx
-- (Excel limits sheet names to 31 characters).
-- =============================================================


-- name: Category Revenue
-- Total revenue, order count and revenue share per category
SELECT
    category,
    COUNT(*) AS total_items_sold,
    COUNT(DISTINCT order_id) AS total_orders,
    ROUND(SUM(sales), 2) AS total_revenue,
    ROUND(SUM(sales) * 100.0 / SUM(SUM(sales)) OVER(), 2) AS pct_of_total_revenue
FROM Sales
GROUP BY category
ORDER BY total_revenue DESC;


-- name: Category Stats
-- Descriptive statistics of sales per category
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


-- name: Top 3 Sales in Category
-- Three highest sales in each category (window function: DENSE_RANK)
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


-- name: MoM Growth
-- Month-over-month sales change and growth % (window function: LAG)
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


-- name: Underperforming Subcategories
-- Flags sub-categories whose total sales fall below the average sub-category
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


-- name: Category Benchmarks
-- Compares each category's total sales to the average category
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
