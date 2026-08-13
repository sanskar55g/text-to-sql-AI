USE olist;

-- 1. Load Users 
LOAD DATA INFILE 'path_to_/olist_customers_dataset.csv'
INTO TABLE users
FIELDS TERMINATED BY ',' ENCLOSED BY '"' LINES TERMINATED BY '\n'
IGNORE 1 ROWS;

-- 2. Load Products 
LOAD DATA INFILE 'path_to_/olist_products_dataset.csv'
INTO TABLE products
FIELDS TERMINATED BY ',' ENCLOSED BY '"' LINES TERMINATED BY '\n'
IGNORE 1 ROWS
(product_id, product_category_name, @v_name_len, @v_desc_len, @v_photos, @v_weight, @v_length, @v_height, @v_width)
SET 
product_name_lenght = NULLIF(@v_name_len, ''),
product_description_lenght = NULLIF(@v_desc_len, ''),
product_photos_qty = NULLIF(@v_photos, ''),
product_weight_g = NULLIF(@v_weight, ''),
product_length_cm = NULLIF(@v_length, ''),
product_height_cm = NULLIF(@v_height, ''),
product_width_cm = NULLIF(@v_width, '');

-- 3. Load Orders 
LOAD DATA INFILE 'path_to_/olist_orders_dataset.csv'
INTO TABLE orders
FIELDS TERMINATED BY ',' ENCLOSED BY '"' LINES TERMINATED BY '\n'
IGNORE 1 ROWS
(order_id, customer_id, order_status, order_purchase_timestamp, @v_approved, @v_carrier, @v_customer, @v_estimated)
SET 
order_approved_at = NULLIF(@v_approved, ''),
order_delivered_carrier_date = NULLIF(@v_carrier, ''),
order_delivered_customer_date = NULLIF(@v_customer, ''),
order_estimated_delivery_date = NULLIF(@v_estimated, '');

-- 4. Load Order Items
LOAD DATA INFILE 'path_to_/olist_order_items_dataset.csv'
INTO TABLE order_items
FIELDS TERMINATED BY ',' ENCLOSED BY '"' LINES TERMINATED BY '\n'
IGNORE 1 ROWS;
