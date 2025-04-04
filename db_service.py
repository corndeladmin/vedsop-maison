import sqlite3
import os
from flask import current_app

# Global database connection
db = None
db_path = None

def get_db():
    global db, db_path
    if db is None:
        try:
            # Try to get path from Flask config
            db_path = current_app.config['DATABASE']
        except RuntimeError:
            # If outside Flask context, use default path
            db_path = 'data/store.db'
        
        # Ensure parent folder exists
        parent_dir = os.path.dirname(db_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        db = sqlite3.connect(
            db_path,
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        db.row_factory = sqlite3.Row
    return db

def close_db(e=None):
    global db
    if db is not None:
        db.close()
        db = None

def init_app(app):
    # Register close_db to be called when the application shuts down
    app.teardown_appcontext(close_db)

def get_user_by_id(user_id):
    db = get_db()
    return db.execute('SELECT * FROM user WHERE id = ?', (user_id,)).fetchone()

def get_user_by_username(username):
    db = get_db()
    return db.execute('SELECT * FROM user WHERE username = ?', (username,)).fetchone()

def create_user(username, password_hash):
    db = get_db()
    db.execute('INSERT INTO user (username, password_hash) VALUES (?, ?)', (username, password_hash))
    db.commit()

def get_all_products():
    db = get_db()
    return db.execute('SELECT * FROM product').fetchall()

def get_all_products_ordered():
    db = get_db()
    return db.execute('SELECT * FROM product ORDER BY name').fetchall()

def get_featured_products(limit=8):
    db = get_db()
    return db.execute('SELECT * FROM product WHERE stock > 0 ORDER BY RANDOM() LIMIT ?', (limit,)).fetchall()

def get_product_by_id(product_id):
    db = get_db()
    return db.execute('SELECT * FROM product WHERE id = ?', (product_id,)).fetchone()

def get_cart(user_id):
    db = get_db()
    cart = db.execute('SELECT * FROM cart WHERE user_id = ?', (user_id,)).fetchone()
    if not cart:
        db.execute('INSERT INTO cart (user_id) VALUES (?)', (user_id,))
        db.commit()
        cart = db.execute('SELECT * FROM cart WHERE user_id = ?', (user_id,)).fetchone()
    return cart

def get_cart_items(cart_id):
    db = get_db()
    return db.execute('''
        SELECT ci.*, p.name, p.price, p.image_url, p.description 
        FROM cart_item ci 
        JOIN product p ON ci.product_id = p.id 
        WHERE ci.cart_id = ?
    ''', (cart_id,)).fetchall()

def add_to_cart(cart_id, product_id, quantity):
    db = get_db()
    cart_item = db.execute('''
        SELECT * FROM cart_item 
        WHERE cart_id = ? AND product_id = ?
    ''', (cart_id, product_id)).fetchone()
    
    if cart_item:
        db.execute('''
            UPDATE cart_item 
            SET quantity = quantity + ? 
            WHERE id = ?
        ''', (quantity, cart_item['id']))
    else:
        db.execute('''
            INSERT INTO cart_item (cart_id, product_id, quantity) 
            VALUES (?, ?, ?)
        ''', (cart_id, product_id, quantity))
    
    db.commit()

def update_cart_item(item_id, quantity):
    db = get_db()
    if quantity > 0:
        db.execute('UPDATE cart_item SET quantity = ? WHERE id = ?', (quantity, item_id))
    else:
        db.execute('DELETE FROM cart_item WHERE id = ?', (item_id,))
    db.commit()

def remove_cart_item(item_id):
    db = get_db()
    db.execute('DELETE FROM cart_item WHERE id = ?', (item_id,))
    db.commit()

def clear_cart(cart_id):
    db = get_db()
    db.execute('DELETE FROM cart_item WHERE cart_id = ?', (cart_id,))
    db.commit()

def create_order(user_id, total_amount, cart_items, shipping_name, shipping_email, shipping_address):
    db = get_db()
    # Create order
    db.execute('''
        INSERT INTO orders (user_id, total_amount, created_at, shipping_name, shipping_email, shipping_address) 
        VALUES (?, ?, datetime('now'), ?, ?, ?)
    ''', (user_id, total_amount, shipping_name, shipping_email, shipping_address))
    order_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    
    # Add order items
    for item in cart_items:
        db.execute('''
            INSERT INTO order_item (order_id, product_id, quantity, price) 
            VALUES (?, ?, ?, ?)
        ''', (order_id, item['product_id'], item['quantity'], item['price']))
    
    db.commit()
    return order_id

def get_user_order_history(user_id, search=None):
    db = get_db()
    cursor = db.cursor()
    
    if search:
        query = f'''
            SELECT o.*,
                GROUP_CONCAT(p.name || ' (' || oi.quantity || ')') as product_names
            FROM orders o
            LEFT JOIN order_item oi ON o.id = oi.order_id
            LEFT JOIN product p ON oi.product_id = p.id
            WHERE p.name LIKE '%{search}%' AND o.user_id = {user_id}
            GROUP BY o.id
            ORDER BY o.created_at DESC
        '''
    else:
        query = f'''
            SELECT o.*,
                GROUP_CONCAT(p.name || ' (' || oi.quantity || ')') as product_names
            FROM orders o
            LEFT JOIN order_item oi ON o.id = oi.order_id
            LEFT JOIN product p ON oi.product_id = p.id
            WHERE o.user_id = {user_id}
            GROUP BY o.id
            ORDER BY o.created_at DESC
        '''

    cursor.execute(query)
    return cursor.fetchall()

def get_products_by_category(category):
    db = get_db()
    return db.execute('SELECT * FROM product WHERE category = ? AND stock > 0', (category,)).fetchall()

def get_all_orders_with_details():
    db = get_db()
    cursor = db.cursor()
    
    # Get orders with user info and items
    cursor.execute('''
        SELECT o.*, u.username,
               GROUP_CONCAT(p.name || ' (' || oi.quantity || ')') as items_list,
               GROUP_CONCAT(oi.quantity) as quantities,
               GROUP_CONCAT(p.name) as product_names
        FROM orders o
        JOIN user u ON o.user_id = u.id
        LEFT JOIN order_item oi ON o.id = oi.order_id
        LEFT JOIN product p ON oi.product_id = p.id
        GROUP BY o.id
        ORDER BY o.created_at DESC
    ''')
    orders_raw = cursor.fetchall()
    
    # Convert SQLite Row objects to dictionaries and process items
    orders = []
    for order in orders_raw:
        order_dict = dict(order)
        if order_dict['items_list']:
            quantities = order_dict['quantities'].split(',')
            product_names = order_dict['product_names'].split(',')
            order_dict['items'] = [{'quantity': int(q), 'name': n} for q, n in zip(quantities, product_names)]
        else:
            order_dict['items'] = []
        orders.append(order_dict)
    
    return orders

def get_order_details(order_id):
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('''
        SELECT o.*, u.username 
        FROM orders o
        JOIN user u ON o.user_id = u.id
        WHERE o.id = ?
    ''', (order_id,))
    return cursor.fetchone()

def get_order_items(order_id):
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('''
        SELECT oi.*, p.name, p.image_url
        FROM order_item oi
        JOIN product p ON oi.product_id = p.id
        WHERE oi.order_id = ?
    ''', (order_id,))
    return cursor.fetchall()

def get_all_users():
    db = get_db()
    return db.execute('SELECT * FROM user ORDER BY username').fetchall()

def get_total_orders():
    db = get_db()
    return db.execute('SELECT COUNT(*) FROM orders WHERE status != "refunded"').fetchone()[0]

def get_total_revenue():
    db = get_db()
    return db.execute('SELECT COALESCE(SUM(total_amount), 0) FROM orders WHERE status != "refunded"').fetchone()[0]

def get_total_users():
    db = get_db()
    return db.execute('SELECT COUNT(*) FROM user').fetchone()[0]

def get_recent_orders(limit=5):
    db = get_db()
    return db.execute('''
        SELECT o.id, o.total_amount, o.created_at, u.username
        FROM orders o
        JOIN user u ON o.user_id = u.id
        WHERE o.status != "refunded"
        ORDER BY o.created_at DESC
        LIMIT ?
    ''', (limit,)).fetchall()

def get_top_products(limit=5):
    db = get_db()
    return db.execute('''
        SELECT p.name, COUNT(oi.id) as sales, SUM(oi.quantity * oi.price) as revenue
        FROM order_item oi
        JOIN product p ON oi.product_id = p.id
        JOIN orders o ON oi.order_id = o.id
        WHERE o.status != "refunded"
        GROUP BY p.id
        ORDER BY sales DESC
        LIMIT ?
    ''', (limit,)).fetchall()

def update_order_status(order_id, status):
    db = get_db()
    db.execute('UPDATE orders SET status = ? WHERE id = ?', (status, order_id))
    db.commit()

def update_user_admin_status(user_id, is_admin):
    db = get_db()
    db.execute('UPDATE user SET is_admin = ? WHERE id = ?', (is_admin, user_id))
    db.commit()

def add_product(name, description, price, stock, category, image_url):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        'INSERT INTO product (name, description, price, stock, category, image_url) VALUES (?, ?, ?, ?, ?, ?)',
        (name, description, price, stock, category, image_url)
    )
    db.commit()
    return cursor.lastrowid

def update_product(product_id, name, description, price, stock, category, image_url=None):
    db = get_db()
    cursor = db.cursor()
    
    if image_url:
        cursor.execute(
            'UPDATE product SET name = ?, description = ?, price = ?, stock = ?, category = ?, image_url = ? WHERE id = ?',
            (name, description, price, stock, category, image_url, product_id)
        )
    else:
        cursor.execute(
            'UPDATE product SET name = ?, description = ?, price = ?, stock = ?, category = ? WHERE id = ?',
            (name, description, price, stock, category, product_id)
        )
    db.commit()

def delete_product(product_id):
    db = get_db()
    cursor = db.cursor()
    
    # Get product image path before deletion
    cursor.execute('SELECT image_url FROM product WHERE id = ?', (product_id,))
    product = cursor.fetchone()
    
    # Delete product
    cursor.execute('DELETE FROM product WHERE id = ?', (product_id,))
    db.commit()
    
    return product

# Review functions
def add_review(user_id, product_id, rating, comment):
    db = get_db()
    db.execute(
        'INSERT INTO review (user_id, product_id, rating, comment, created_at) VALUES (?, ?, ?, ?, datetime("now"))',
        (user_id, product_id, rating, comment)
    )
    db.commit()

def get_product_reviews(product_id):
    db = get_db()
    return db.execute('''
        SELECT r.*, u.username 
        FROM review r
        JOIN user u ON r.user_id = u.id
        WHERE r.product_id = ?
        ORDER BY r.created_at DESC
    ''', (product_id,)).fetchall()

def get_review_by_id(review_id):
    db = get_db()
    return db.execute('SELECT * FROM review WHERE id = ?', (review_id,)).fetchone()

def update_review(review_id, rating, comment):
    db = get_db()
    db.execute(
        'UPDATE review SET rating = ?, comment = ? WHERE id = ?',
        (rating, comment, review_id)
    )
    db.commit()

def delete_review(review_id):
    db = get_db()
    db.execute('DELETE FROM review WHERE id = ?', (review_id,))
    db.commit()

def get_user_review_for_product(user_id, product_id):
    db = get_db()
    return db.execute(
        'SELECT * FROM review WHERE user_id = ? AND product_id = ?',
        (user_id, product_id)
    ).fetchone()

def get_avg_product_rating(product_id):
    db = get_db()
    result = db.execute(
        'SELECT AVG(rating) as avg_rating, COUNT(*) as review_count FROM review WHERE product_id = ?',
        (product_id,)
    ).fetchone()
    return result
