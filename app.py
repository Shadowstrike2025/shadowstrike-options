import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask
app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'shadowstrike-secret-2025')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///shadowstrike.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Fix for Heroku/Render Postgres URL
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://')

# Initialize database
db = SQLAlchemy(app)

# User Model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    subscription_status = db.Column(db.String(20), default='trial')
    trial_end_date = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(days=30))

# Trade Model
class Trade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    symbol = db.Column(db.String(10), nullable=False)
    option_type = db.Column(db.String(4), nullable=False)  # CALL or PUT
    strike_price = db.Column(db.Float, nullable=False)
    entry_price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    entry_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(10), default='open')  # open or closed
    
    user = db.relationship('User', backref='trades')

# Routes
@app.route('/')
def index():
    try:
        return render_template('welcome.html')
    except Exception as e:
        logger.error(f"Error rendering welcome.html: {e}")
        return f"""
        <h1>🎯 ShadowStrike Options</h1>
        <p>Platform is running! Template error: {e}</p>
        <a href="/login">Login</a> | <a href="/register">Register</a> | <a href="/status">Status</a>
        """

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    try:
        return render_template('login.html')
    except Exception as e:
        logger.error(f"Error rendering login.html: {e}")
        return f"""
        <h1>🎯 ShadowStrike Options - Login</h1>
        <p>Template error: {e}</p>
        <form method="POST">
            <input name="username" placeholder="Username" required><br><br>
            <input name="password" type="password" placeholder="Password" required><br><br>
            <button type="submit">Login</button>
        </form>
        <a href="/">Home</a> | <a href="/register">Register</a>
        """

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        terms = request.form.get('terms_accepted')
        
        # Validation
        if not all([username, email, password]):
            flash('All fields are required', 'error')
            return redirect(url_for('register'))
        
        if not terms:
            flash('You must accept the terms and conditions', 'error')
            return redirect(url_for('register'))
        
        # Check if user exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return redirect(url_for('register'))
        
        # Create new user
        try:
            user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password)
            )
            db.session.add(user)
            db.session.commit()
            
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            logger.error(f"Registration error: {e}")
            flash('Registration failed. Please try again.', 'error')
    
    try:
        return render_template('register.html')
    except Exception as e:
        logger.error(f"Error rendering register.html: {e}")
        return f"""
        <h1>🎯 ShadowStrike Options - Register</h1>
        <p>Template error: {e}</p>
        <form method="POST">
            <input name="username" placeholder="Username" required><br><br>
            <input name="email" type="email" placeholder="Email" required><br><br>
            <input name="password" type="password" placeholder="Password" required><br><br>
            <input name="terms_accepted" type="checkbox" required> I accept terms<br><br>
            <button type="submit">Register</button>
        </form>
        <a href="/">Home</a> | <a href="/login">Login</a>
        """

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please login to access the dashboard', 'error')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('User not found. Please login again.', 'error')
        return redirect(url_for('login'))
    
    # Get user's trades
    trades = Trade.query.filter_by(user_id=user.id).all()
    
    # Calculate portfolio stats
    total_pnl = 0
    open_trades = 0
    for trade in trades:
        if trade.status == 'open':
            open_trades += 1
            # Simple P&L calculation (in real app, you'd get current prices)
            current_price = trade.entry_price * 1.1  # Mock 10% gain
            pnl = (current_price - trade.entry_price) * trade.quantity * 100
            total_pnl += pnl
    
    try:
        return render_template('dashboard.html', 
                             user=user, 
                             trades=trades, 
                             total_pnl=total_pnl,
                             open_trades=open_trades)
    except Exception as e:
        logger.error(f"Error rendering dashboard.html: {e}")
        return f"""
        <h1>🎯 ShadowStrike Options - Dashboard</h1>
        <p>Welcome {user.username}!</p>
        <p>Template error: {e}</p>
        <p>Portfolio P&L: ${total_pnl:.2f}</p>
        <p>Open Trades: {open_trades}</p>
        <a href="/logout">Logout</a>
        """

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

@app.route('/status')
def status():
    total_users = User.query.count()
    total_trades = Trade.query.count()
    
    try:
        return render_template('status.html', 
                             total_users=total_users,
                             total_trades=total_trades)
    except Exception as e:
        logger.error(f"Error rendering status.html: {e}")
        return f"""
        <h1>🎯 ShadowStrike Options - Status</h1>
        <p>Platform Status: ✅ LIVE</p>
        <p>Total Users: {total_users}</p>
        <p>Total Trades: {total_trades}</p>
        <p>Template error: {e}</p>
        <a href="/">Home</a>
        """

# API Routes
@app.route('/api/portfolio')
def api_portfolio():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    trades = Trade.query.filter_by(user_id=session['user_id']).all()
    portfolio_data = []
    
    for trade in trades:
        # Mock current price calculation
        current_price = trade.entry_price * (1 + (hash(trade.symbol) % 20 - 10) / 100)
        pnl = (current_price - trade.entry_price) * trade.quantity * 100
        
        portfolio_data.append({
            'id': trade.id,
            'symbol': trade.symbol,
            'option_type': trade.option_type,
            'strike_price': trade.strike_price,
            'entry_price': trade.entry_price,
            'current_price': round(current_price, 2),
            'quantity': trade.quantity,
            'pnl': round(pnl, 2),
            'status': trade.status,
            'entry_date': trade.entry_date.strftime('%Y-%m-%d')
        })
    
    return jsonify(portfolio_data)

# Debug route to check templates
@app.route('/debug')
def debug():
    import os
    template_dir = app.template_folder
    if os.path.exists(template_dir):
        files = os.listdir(template_dir)
        return f"Template directory exists: {template_dir}<br>Files: {files}"
    else:
        return f"Template directory NOT found: {template_dir}"

# Initialize database
def create_tables():
    with app.app_context():
        try:
            db.create_all()
            
            # Create demo admin user if doesn't exist
            if not User.query.filter_by(username='admin').first():
                admin = User(
                    username='admin',
                    email='admin@shadowstrike.com',
                    password_hash=generate_password_hash('admin123')
                )
                db.session.add(admin)
                db.session.commit()
                logger.info("Created admin user: admin/admin123")
        except Exception as e:
            logger.error(f"Database initialization error: {e}")

if __name__ == '__main__':
    create_tables()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
