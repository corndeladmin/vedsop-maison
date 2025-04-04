from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime
from db_service import (
    get_user_by_id, get_user_by_username, create_user,
    get_all_products, get_product_by_id, get_cart, get_cart_items, add_to_cart,
    update_cart_item, remove_cart_item, clear_cart, create_order,
    get_products_by_category, get_total_orders, get_total_revenue, get_total_users,
    get_recent_orders, get_top_products, update_order_status, get_order_details,
    get_order_items, get_all_users, get_all_orders_with_details, update_user_admin_status,
    get_featured_products, get_user_order_history, add_product, update_product, delete_product,
    get_all_products_ordered, add_review, get_product_reviews, get_review_by_id, 
    update_review, delete_review, get_user_review_for_product, get_avg_product_rating
)
from functools import wraps
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['DATABASE'] = 'data/store.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.jinja_env.autoescape = False

# Create upload directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize database service
from db_service import init_app
init_app(app)

# Ensure database exists and is populated
with app.app_context():
    if not os.path.exists(app.config['DATABASE']):
        from populate_db import populate_database
        populate_database()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, user_id, username, password_hash, role=False):
        self.id = user_id
        self.username = username
        self.password_hash = password_hash
        self._role = role
    
    @property
    def is_admin(self):
        role_cookie = request.cookies.get('role')
        if role_cookie and role_cookie == 'admin':
            return True
        return False

@login_manager.user_loader
def load_user(user_id):
    user = get_user_by_id(user_id)
    if user:
        return User(user['id'], user['username'], user['password_hash'], user['is_admin'])
    return None

@app.route('/category/<category>')
def category(category):
    products = get_products_by_category(category)
    return render_template('category.html', products=products, category=category)

@app.route('/')
def index():
    featured_products = get_featured_products(8)  # Get 8 random products
    return render_template('index.html', products=featured_products)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = get_user_by_username(username)
        
        if user and check_password_hash(user['password_hash'], password):
            user_obj = User(user['id'], user['username'], user['password_hash'], user['is_admin'])
            login_user(user_obj)
            
            # Create response and set cookie with admin status
            response = make_response(redirect(url_for('index')))
            response.set_cookie('role', 'admin' if user['is_admin'] else 'user')
            return response
            
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if get_user_by_username(username):
            flash('Username already exists')
            return redirect(url_for('register'))
        
        create_user(username, generate_password_hash(password))
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    response = make_response(redirect(url_for('index')))
    response.set_cookie('role', 'user', expires=0)  # Clear the cookie
    return response

@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart_route(product_id):
    quantity = int(request.form.get('quantity', 1))
    product = get_product_by_id(product_id)
    
    if not product:
        flash('Product not found', 'error')
        return redirect(url_for('index'))
    
    cart = get_cart(current_user.id)
    add_to_cart(cart['id'], product_id, quantity)
    flash(f'Added {quantity} {product["name"]} to your cart', 'success')
    return redirect(url_for('index'))

@app.route('/cart')
@login_required
def view_cart():
    cart = get_cart(current_user.id)
    cart_items = get_cart_items(cart['id'])
    total = sum(item['price'] * item['quantity'] for item in cart_items)
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/update_cart/<int:item_id>', methods=['POST'])
@login_required
def update_cart(item_id):
    cart = get_cart(current_user.id)
    action = request.form.get('action')
    
    if action == 'update':
        quantity = int(request.form.get('quantity', 1))
        update_cart_item(item_id, quantity)
    elif action == 'remove':
        remove_cart_item(item_id)
    
    return redirect(url_for('view_cart'))

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    cart = get_cart(current_user.id)
    cart_items = get_cart_items(cart['id'])
    
    if not cart_items:
        flash('Your cart is empty', 'error')
        return redirect(url_for('index'))
    
    total = sum(item['price'] * item['quantity'] for item in cart_items)
    
    if request.method == 'POST':
        shipping_name = request.form.get('full_name')
        shipping_email = request.form.get('email')
        shipping_address = request.form.get('address')
        
        if not all([shipping_name, shipping_email, shipping_address]):
            flash('Please fill in all shipping information', 'error')
            return redirect(url_for('checkout'))
        
        create_order(current_user.id, total, cart_items, shipping_name, shipping_email, shipping_address)
        clear_cart(cart['id'])
        flash('Order placed successfully!', 'success')
        return redirect(url_for('order_history'))
    
    return render_template('checkout.html', cart_items=cart_items, total=total)

@app.route('/order_history')
@login_required
def order_history():
    search = request.args.get('search', '')
    orders = get_user_order_history(current_user.id, search)
    return render_template('order_history.html', orders=orders, now=datetime.now(), search=search)

@app.route('/order_details/<int:order_id>')
@login_required
def order_details(order_id):
    # Get order details
    order = get_order_details(order_id)
    
    if not order:
        flash('Order not found', 'error')
        return redirect(url_for('order_history'))
    
    # Get order items
    items = get_order_items(order_id)
    
    return render_template('order_details.html', order=order, items=items, now=datetime.now())

@app.context_processor
def inject_cart_items():
    cart_items = []
    if current_user.is_authenticated:
        cart = get_cart(current_user.id)
        cart_items = get_cart_items(cart['id'])
    return dict(cart_items=cart_items)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin/products')
@login_required
@admin_required
def admin_products():
    products = get_all_products_ordered()
    
    # Get ratings for each product
    products_with_ratings = []
    for product in products:
        product_dict = dict(product)
        rating_data = get_avg_product_rating(product['id'])
        product_dict['avg_rating'] = round(rating_data['avg_rating'], 1) if rating_data['avg_rating'] else 0
        product_dict['review_count'] = rating_data['review_count']
        products_with_ratings.append(product_dict)
    
    return render_template('admin/products.html', products=products_with_ratings)

@app.route('/admin/products/add', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_add_product():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = float(request.form['price'])
        stock = int(request.form['stock'])
        category = request.form['category']
        
        # Handle image upload
        image_url = None
        if 'image' in request.files:
            file = request.files['image']
            if file.filename:
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                image_url = url_for('static', filename=f'uploads/{filename}')
        
        add_product(name, description, price, stock, category, image_url)
        flash('Product added successfully!', 'success')
        return redirect(url_for('admin_products'))
    
    return render_template('admin/product_form.html')

@app.route('/admin/products/<int:product_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_product(product_id):
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = float(request.form['price'])
        stock = int(request.form['stock'])
        category = request.form['category']
        
        # Handle image upload
        image_url = None
        if 'image' in request.files:
            file = request.files['image']
            if file.filename:
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                image_url = url_for('static', filename=f'uploads/{filename}')
        
        update_product(product_id, name, description, price, stock, category, image_url)
        flash('Product updated successfully!', 'success')
        return redirect(url_for('admin_products'))
    
    product = get_product_by_id(product_id)
    if not product:
        flash('Product not found.', 'error')
        return redirect(url_for('admin_products'))
    
    return render_template('admin/product_form.html', product=product)

@app.route('/admin/products/<int:product_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_product(product_id):
    product = delete_product(product_id)
    
    # Delete associated image file if exists
    if product and product['image_url']:
        try:
            image_path = os.path.join(app.root_path, 'static', product['image_url'].lstrip('/'))
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception as e:
            app.logger.error(f'Error deleting image file: {e}')
    
    flash('Product deleted successfully!', 'success')
    return redirect(url_for('admin_products'))

@app.route('/admin/orders')
@login_required
@admin_required
def admin_orders():
    orders = get_all_orders_with_details()
    return render_template('admin/orders.html', orders=orders)

@app.route('/admin/orders/<int:order_id>')
@login_required
@admin_required
def admin_order_details(order_id):
    order = get_order_details(order_id)
    
    if not order:
        flash('Order not found', 'error')
        return redirect(url_for('admin_orders'))
    
    items = get_order_items(order_id)
    return render_template('admin/order_details.html', order=order, items=items)

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = get_all_users()
    return render_template('admin/users.html', users=users)

@app.route('/admin/stats')
@login_required
@admin_required
def admin_stats():
    total_orders = get_total_orders()
    total_revenue = get_total_revenue()
    total_users = get_total_users()
    recent_orders = get_recent_orders(5)
    top_products = get_top_products(5)
    
    return render_template('admin/stats.html',
                         total_orders=total_orders,
                         total_revenue=total_revenue,
                         total_users=total_users,
                         recent_orders=recent_orders,
                         top_products=top_products,
                         now=datetime.now())

@app.route('/admin/users/<int:user_id>/toggle-admin', methods=['POST'])
@login_required
@admin_required
def toggle_admin(user_id):
    if current_user.id == user_id:
        return jsonify({'success': False, 'message': 'Cannot modify your own admin status'})
    
    data = request.get_json()
    make_admin = data.get('make_admin', False)
    
    update_user_admin_status(user_id, make_admin)
    
    return jsonify({'success': True})

@app.route('/orders/<int:order_id>/refund', methods=['POST'])
@login_required
def refund_order(order_id):
    order = get_order_details(order_id)
    
    if not order:
        return jsonify({'success': False, 'message': 'Order not found'})
    
    # Check if order is already refunded
    if order['status'] == 'refunded':
        return jsonify({'success': False, 'message': 'Order is already refunded'})
    
    update_order_status(order_id, 'refunded')
    
    return jsonify({'success': True})

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = get_product_by_id(product_id)
    if not product:
        flash('Product not found', 'error')
        return redirect(url_for('index'))
    
    reviews = get_product_reviews(product_id)
    rating_data = get_avg_product_rating(product_id)
    avg_rating = round(rating_data['avg_rating'], 1) if rating_data['avg_rating'] else 0
    review_count = rating_data['review_count']
    
    user_review = None
    if current_user.is_authenticated:
        user_review = get_user_review_for_product(current_user.id, product_id)
    
    return render_template('product_detail.html', 
                          product=product, 
                          reviews=reviews, 
                          avg_rating=avg_rating, 
                          review_count=review_count,
                          user_review=user_review)

@app.route('/product/<int:product_id>/review', methods=['POST'])
@login_required
def add_product_review(product_id):
    product = get_product_by_id(product_id)
    if not product:
        flash('Product not found', 'error')
        return redirect(url_for('index'))
    
    rating = int(request.form.get('rating', 5))
    comment = request.form.get('comment', '')
    
    # Check if user already reviewed this product
    existing_review = get_user_review_for_product(current_user.id, product_id)
    
    if existing_review:
        update_review(existing_review['id'], rating, comment)
        flash('Your review has been updated', 'success')
    else:
        add_review(current_user.id, product_id, rating, comment)
        flash('Your review has been added', 'success')
    
    return redirect(url_for('product_detail', product_id=product_id))

@app.route('/review/<int:review_id>/delete', methods=['POST'])
@login_required
def delete_product_review(review_id):
    review = get_review_by_id(review_id)
    
    if not review:
        flash('Review not found', 'error')
        return redirect(url_for('index'))
    
    # Check if the user owns the review or is an admin
    if review['user_id'] != current_user.id and not current_user.is_admin:
        flash('You do not have permission to delete this review', 'error')
        return redirect(url_for('product_detail', product_id=review['product_id']))
    
    delete_review(review_id)
    flash('Review deleted successfully', 'success')
    return redirect(url_for('product_detail', product_id=review['product_id']))

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    app.run(host='0.0.0.0', port=args.port, debug=True)
