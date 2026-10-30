-- Primary, unique and foreign keys of core (search_path = core).
--
-- Only these key indexes exist: secondary indexes are the subject of the benchmark experiments, so
-- the baseline must not include any. PostgreSQL does not index the referencing side of a foreign key
-- automatically.
--
-- Foreign keys are DEFERRABLE (but INITIALLY IMMEDIATE): ordinary statements are checked at once,
-- while the publish transaction defers them to its commit. That lets one MERGE per table insert,
-- update and delete rows in any table order, and the whole new version is checked once at the end.
--
-- Primary keys stay immediate: foreign keys reference them, and they cannot collide during a publish,
-- because each MERGE matches on the primary key (a key in both versions is updated in place, never
-- deleted and inserted, and the update leaves the key alone). Any other unique key must be DEFERRABLE
-- for the same reason as the foreign keys: PostgreSQL checks an immediate unique key row by row, so
-- two rows exchanging their values would collide halfway through the MERGE although the new version
-- is valid (tests/test_load.py).

ALTER TABLE product_categories ADD PRIMARY KEY (product_category_name);
ALTER TABLE customers          ADD PRIMARY KEY (customer_id);
ALTER TABLE sellers            ADD PRIMARY KEY (seller_id);
ALTER TABLE products           ADD PRIMARY KEY (product_id);
ALTER TABLE orders             ADD PRIMARY KEY (order_id);
ALTER TABLE order_items        ADD PRIMARY KEY (order_id, order_item_id);
ALTER TABLE order_payments     ADD PRIMARY KEY (order_id, payment_sequential);
ALTER TABLE reviews            ADD PRIMARY KEY (review_id);
ALTER TABLE order_reviews      ADD PRIMARY KEY (order_id, review_id);
ALTER TABLE zip_prefix_geo     ADD PRIMARY KEY (zip_code_prefix);

-- customer_id identifies the buyer of exactly one order (the real person is customer_unique_id).
-- Deferrable, so the planner does not use it to prove uniqueness (join removal, unique inner joins);
-- no foreign key references it, which a deferrable key would not allow.
ALTER TABLE orders ADD CONSTRAINT orders_customer_id_key UNIQUE (customer_id) DEFERRABLE;

ALTER TABLE products       ADD FOREIGN KEY (product_category_name) REFERENCES product_categories DEFERRABLE;
ALTER TABLE orders         ADD FOREIGN KEY (customer_id) REFERENCES customers DEFERRABLE;
ALTER TABLE order_items    ADD FOREIGN KEY (order_id)    REFERENCES orders DEFERRABLE,
                           ADD FOREIGN KEY (product_id)  REFERENCES products DEFERRABLE,
                           ADD FOREIGN KEY (seller_id)   REFERENCES sellers DEFERRABLE;
ALTER TABLE order_payments ADD FOREIGN KEY (order_id)    REFERENCES orders DEFERRABLE;
ALTER TABLE order_reviews  ADD FOREIGN KEY (order_id)    REFERENCES orders DEFERRABLE,
                           ADD FOREIGN KEY (review_id)   REFERENCES reviews DEFERRABLE;
